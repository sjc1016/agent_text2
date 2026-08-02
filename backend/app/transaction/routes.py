"""B6 办理类业务 REST 路由（/transactions/*，Customer 认证）。

PRD 依据：
  - 实现决策 › API 契约（/transactions/* 办理类业务能力发起）
  - 实现决策 › 办理流程（发起 → 二次确认 → 入队 → 执行复核 → 执行）
  - 测试决策 › HTTP 集成 seam（请求/响应形状、状态码、鉴权边界）
  - CONTEXT.md › 办理规则 / 审计日志 / 会话状态机
  - 用户故事 US-8~US-12

端点：
  POST /transactions/plan-change     — 发起套餐变更（US-8）
  POST /transactions/vadd-change     — 发起增值业务订退（US-9）
  POST /transactions/suspend-hold    — 发起停机保号（US-10）
  POST /transactions/recharge        — 发起充值缴费（US-11）
  POST /transactions/confirm         — 二次确认 → 创建 Ticket(Pending) 入队
  POST /transactions/{ticket_id}/execute — 执行（需 execute_token，/auth/reauth 复核后）

发起端点：返回结构化业务影响，推送 WS second.confirm + conversation.state
（会话进入 In-Progress）；确认端点创建 Ticket 入队并回退 Authenticated；
执行端点复核通过后 Processing → 执行 → Effective，推送 ticket.update + notification.push。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.audit import write_audit_log
from app.auth.dependencies import CurrentCustomer, CurrentExecuteCustomer
from app.conversation.service import get_customer_conversation_or_none
from app.db import get_db
from app.models import Customer, Ticket
from app.ticket.schemas import TicketOut
from app.ticket.service import (
    create_notification,
    notification_message,
    should_push_notification,
)
from app.transaction.schemas import (
    PlanChangeRequest,
    RechargeRequest,
    SuspendHoldRequest,
    TransactionConfirmRequest,
    TransactionInitiateOut,
    VaddChangeRequest,
)
from app.transaction.service import (
    confirm_transaction,
    execute_transaction,
    initiate_transaction,
    trigger_execution_reauth,
)
from app.ws.hub import (
    push_conversation_state,
    push_notification,
    push_reauth_required,
    push_second_confirm,
    push_ticket_update,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])

DbSession = Annotated[Session, Depends(get_db)]


async def _initiate(
    db: Session,
    current: Customer,
    transaction_type: str,
    conversation_id: int,
    params: dict,
) -> TransactionInitiateOut:
    """统一发起流程：会话归属校验 → 服务层发起（会话进入 In-Progress）→ 审计 + WS 推送。

    成功：推送 second.confirm（结构化业务影响）+ conversation.state（→ in_progress）。
    会话不存在/不属于当前客户 → 404；发起失败（参数/状态非法）→ 422，状态不变更。
    """
    conv = get_customer_conversation_or_none(db, current, conversation_id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    old_state = conv.status
    try:
        impact = initiate_transaction(db, current, conv, transaction_type, params)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"发起办理失败：{exc}"
        ) from exc

    db.commit()
    db.refresh(conv)
    write_audit_log(
        db,
        actor_type="customer",
        actor_id=current.id,
        action="transaction.initiate",
        detail={"conversation_id": conv.id, "transaction_type": transaction_type},
    )
    await push_second_confirm(conv, impact)
    await push_conversation_state(conv, old_state)
    return TransactionInitiateOut(
        conversation_id=conv.id,
        transaction_type=transaction_type,
        business_impact=impact,
    )


@router.post("/plan-change", response_model=TransactionInitiateOut)
async def plan_change(
    payload: PlanChangeRequest, current: CurrentCustomer, db: DbSession
) -> TransactionInitiateOut:
    """发起套餐变更（US-8）：二次确认（套餐对比/生效时间/合约影响/费用变化）。"""
    return await _initiate(
        db, current, "plan_change", payload.conversation_id, {"target_plan": payload.target_plan}
    )


@router.post("/vadd-change", response_model=TransactionInitiateOut)
async def vadd_change(
    payload: VaddChangeRequest, current: CurrentCustomer, db: DbSession
) -> TransactionInitiateOut:
    """发起增值业务订退（US-9）。"""
    return await _initiate(
        db,
        current,
        "vadd_change",
        payload.conversation_id,
        {"service_name": payload.service_name, "action": payload.action},
    )


@router.post("/suspend-hold", response_model=TransactionInitiateOut)
async def suspend_hold(
    payload: SuspendHoldRequest, current: CurrentCustomer, db: DbSession
) -> TransactionInitiateOut:
    """发起停机保号（US-10）。"""
    return await _initiate(db, current, "suspend_hold", payload.conversation_id, {})


@router.post("/recharge", response_model=TransactionInitiateOut)
async def recharge(
    payload: RechargeRequest, current: CurrentCustomer, db: DbSession
) -> TransactionInitiateOut:
    """发起充值缴费（US-11）。"""
    return await _initiate(
        db, current, "recharge", payload.conversation_id, {"amount": payload.amount}
    )


@router.post("/confirm", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def confirm(
    payload: TransactionConfirmRequest, current: CurrentCustomer, db: DbSession
) -> Ticket:
    """二次确认 → 创建办理类 Ticket(Pending) 入队，会话回退 Authenticated（US-8）。

    未确认不入队（CONTEXT › 办理入队）；一律经 Ticket，不直接生效。
    """
    conv = get_customer_conversation_or_none(db, current, payload.conversation_id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    old_state = conv.status
    try:
        ticket = confirm_transaction(db, current, conv, payload.content)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"确认办理失败：{exc}"
        ) from exc

    db.commit()
    db.refresh(ticket)
    db.refresh(conv)
    write_audit_log(
        db,
        actor_type="customer",
        actor_id=current.id,
        action="transaction.confirm",
        detail={"conversation_id": conv.id, "ticket_id": ticket.id},
    )
    await push_conversation_state(conv, old_state)
    return ticket


@router.post("/{ticket_id}/reauth", response_model=TicketOut)
async def request_reauth(ticket_id: int, current: CurrentCustomer, db: DbSession) -> Ticket:
    """触发办理执行前服务密码复核（US-12）。

    调度任务 seam 的 REST 暴露（PRD 测试决策 › 调度任务 seam：Ticket 待执行 →
    执行中触发服务密码复核）：校验通过后推送 reauth.required（WS），提示用户再次
    输入服务密码；随后经 /auth/reauth 复核取得 execute_token，凭之调用 execute 端点。
    """
    ticket = db.get(Ticket, ticket_id)
    if ticket is None or ticket.customer_id != current.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工单不存在")

    try:
        trigger_execution_reauth(db, current, ticket)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"触发执行复核失败：{exc}",
        ) from exc

    db.commit()
    db.refresh(ticket)
    write_audit_log(
        db,
        actor_type="customer",
        actor_id=current.id,
        action="transaction.reauth_request",
        detail={"ticket_id": ticket.id},
    )
    await push_reauth_required(ticket)
    return ticket


@router.post("/{ticket_id}/execute", response_model=TicketOut)
async def execute(ticket_id: int, current: CurrentExecuteCustomer, db: DbSession) -> Ticket:
    """执行办理（US-12）：execute_token 复核通过后 Processing → 执行 → Effective。

    access token 调本端点 → 401（未复核不得执行，CONTEXT › 办理执行复核）；
    执行成功后推送 ticket.update + notification.push（生效通知）。
    """
    ticket = db.get(Ticket, ticket_id)
    if ticket is None or ticket.customer_id != current.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工单不存在")

    old_status = ticket.status.value
    try:
        execute_transaction(db, ticket)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"执行办理失败：{exc}"
        ) from exc

    notification = None
    if should_push_notification(ticket, ticket.status.value):
        notification = create_notification(
            db, ticket, notification_message(ticket, ticket.status.value)
        )

    db.commit()
    db.refresh(ticket)
    if notification is not None:
        db.refresh(notification)
    write_audit_log(
        db,
        actor_type="customer",
        actor_id=current.id,
        action="transaction.execute",
        detail={"ticket_id": ticket.id},
    )
    await push_ticket_update(ticket, old_status)
    if notification is not None:
        await push_notification(notification)
    return ticket
