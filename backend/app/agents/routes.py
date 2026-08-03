"""坐席 REST 路由（/agents/login、/agents/status、/agents/queues）。

B9（issue #15）：
  POST /agents/login  — 工号+密码登录，颁发坐席 JWT（US-19）
  PUT  /agents/status — 切换在线/离线/小休（US-30；WS agent.status 推送走 WS seam）
  GET  /agents/queues — 待接入 Handoff 会话列表（US-20）

PRD 依据：实现决策 › API 契约 /agents/*；测试决策 › HTTP 集成 seam。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agents.schemas import (
    AgentCustomerProfileOut,
    AgentExecuteRequest,
    AgentLoginRequest,
    AgentPublic,
    AgentStatusUpdate,
    AgentTicketOut,
    CallbackItemOut,
    ConversationViewOut,
    QueueItemOut,
)
from app.agents.service import (
    authenticate_agent,
    execute_ticket_after_agent_reauth,
    get_agent_conversation_or_none,
    get_customer_profile,
    list_all_tickets,
    list_callback_tickets,
    list_pending_queue_entries,
    mask_phone,
)
from app.agents.service import (
    list_conversation_tickets as list_conversation_tickets_service,
)
from app.auth.audit import write_audit_log
from app.auth.dependencies import CurrentAgent
from app.auth.schemas import TokenResponse
from app.auth.security import create_agent_access_token, create_agent_refresh_token
from app.conversation.schemas import MessageOut
from app.conversation.service import list_messages_for_conversation
from app.db import get_db
from app.models import Customer, Message, Notification, Ticket, User
from app.ticket.schemas import TicketCreate, TicketOut
from app.ticket.service import (
    create_notification,
    create_ticket,
    notification_message,
    should_push_notification,
    transition_ticket_status,
)
from app.ws.hub import push_agent_status, push_notification, push_ticket_update

router = APIRouter(prefix="/agents", tags=["agents"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post("/login", response_model=TokenResponse)
def agent_login(payload: AgentLoginRequest, db: DbSession) -> TokenResponse:
    """工号+密码登录 → 颁发坐席 JWT；成功/失败均记审计（CONTEXT › 审计日志）。"""
    agent = authenticate_agent(db, payload.employee_id, payload.password)
    if agent is None:
        write_audit_log(
            db,
            actor_type="agent",
            action="agent.login.failure",
            detail={"employee_id": payload.employee_id},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="工号或密码错误",
        )
    write_audit_log(
        db,
        actor_type="agent",
        actor_id=agent.id,
        action="agent.login.success",
    )
    return TokenResponse(
        access_token=create_agent_access_token(agent.id),
        refresh_token=create_agent_refresh_token(agent.id),
    )


@router.put("/status", response_model=AgentPublic)
async def update_agent_status(
    payload: AgentStatusUpdate, db: DbSession, current: CurrentAgent
) -> User:
    """切换坐席状态（在线/离线/小休，US-30）。

    坐席 JWT 保护（CurrentAgent）；非法状态由 schema Literal 转 422。
    db.commit 后经 hub 向该坐席活跃 WS 连接推送 agent.status
    （REST 与 WS 独立连接，推送方不在 WS 上下文内 —— 复用 B7 hub 模式）。
    """
    current.status = payload.status
    db.commit()
    write_audit_log(
        db,
        actor_type="agent",
        actor_id=current.id,
        action="agent.status.update",
        detail={"status": payload.status},
    )
    db.refresh(current)
    await push_agent_status(current, payload.status)
    return current


@router.get("/queues", response_model=list[QueueItemOut])
def list_pending_queues(db: DbSession, current: CurrentAgent) -> list[QueueItemOut]:
    """待接入 Handoff 会话列表（US-20）。

    仅返回 handed_off 且未被接入的会话；号码脱敏（138****0001）；
    每项含转接原因（Conversation.handoff_reason，PRD queue 页转接原因 Caption）。
    """
    return [
        QueueItemOut(
            conversation_id=entry.conversation.id,
            status=entry.conversation.status,
            created_at=entry.conversation.created_at,
            customer_id=entry.conversation.customer_id,
            customer_phone=entry.customer_phone,
            last_user_message=entry.last_user_message,
            reason=entry.conversation.handoff_reason,
        )
        for entry in list_pending_queue_entries(db)
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationViewOut)
def get_conversation_view(
    conversation_id: int, db: DbSession, current: CurrentAgent
) -> ConversationViewOut:
    """坐席读单会话视图（US-21）：会话状态 + 脱敏号码 + 转接原因。

    B14（issue #55 AC4）：active-chat 页会话上下文数据源；可见性规则复用
    消息历史（仅 handed_off 转接中的会话对坐席可见，否则 404，不泄露会话存在性）。
    """
    conv = get_agent_conversation_or_none(db, conversation_id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")

    customer_phone = None
    if conv.customer_id is not None:
        customer = db.get(Customer, conv.customer_id)
        if customer is not None:
            customer_phone = mask_phone(customer.phone)

    return ConversationViewOut(
        conversation_id=conv.id,
        status=conv.status,
        customer_id=conv.customer_id,
        customer_phone=customer_phone,
        handoff_reason=conv.handoff_reason,
        created_at=conv.created_at,
    )


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_conversation_messages(
    conversation_id: int, db: DbSession, current: CurrentAgent
) -> list[Message]:
    """坐席读取转接会话消息历史（US-21，B12 issue #44 AC1）。

    仅 handed_off 转接中的会话对坐席可见（转回助理后不可读）；会话不存在
    或非 handed_off → 404（不泄露客户会话存在性）。
    """
    conv = get_agent_conversation_or_none(db, conversation_id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return list_messages_for_conversation(db, conversation_id)


@router.get("/conversations/{conversation_id}/tickets", response_model=list[TicketOut])
def list_conversation_tickets(
    conversation_id: int, db: DbSession, current: CurrentAgent
) -> list[Ticket]:
    """坐席查询会话所属工单列表（US-23，B12 issue #44 AC3）。

    active-chat 右栏「当前工单」数据源；会话可见性同消息历史（仅 handed_off）。
    """
    conv = get_agent_conversation_or_none(db, conversation_id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return list_conversation_tickets_service(db, conversation_id)


@router.post("/tickets", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def create_agent_ticket(payload: TicketCreate, db: DbSession, current: CurrentAgent) -> Ticket:
    """坐席为转接会话创建工单（US-23，B12 issue #44 AC3）。

    creator_type=agent、creator_id=坐席；customer_id 关联会话所属客户（访客会话
    为 None 仅落联系方式）。仅 handed_off 转接中的会话可建单（坐席在 active-chat
    右栏「创建工单」Modal 提交）。
    """
    conv = get_agent_conversation_or_none(db, payload.conversation_id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    ticket = create_ticket(
        db,
        conversation_id=conv.id,
        ticket_type=payload.ticket_type,
        content=payload.content,
        creator_type="agent",
        creator_id=current.id,
        customer_id=conv.customer_id,
    )
    db.commit()
    db.refresh(ticket)
    write_audit_log(
        db,
        actor_type="agent",
        actor_id=current.id,
        action="agent.ticket.create",
        detail={"conversation_id": conv.id, "ticket_id": ticket.id},
    )
    return ticket


@router.get("/customers/{customer_id}", response_model=AgentCustomerProfileOut)
def customer_profile(
    customer_id: int, db: DbSession, current: CurrentAgent
) -> AgentCustomerProfileOut:
    """坐席读取客户资料 + 账户信息（US-21，B12 issue #44 AC2）。

    active-chat 右栏客户标识卡 + 账户信息块数据源；号码脱敏（138****0001）。
    访客（无 Customer）或无账户记录 → 404；敏感数据访问写审计日志
    （CONTEXT › 审计日志 › 用户敏感数据）。
    """
    profile = get_customer_profile(db, customer_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客户不存在或无账户")
    customer, account = profile
    write_audit_log(
        db,
        actor_type="agent",
        actor_id=current.id,
        action="agent.customer_profile_access",
        detail={"customer_id": customer.id},
    )
    return AgentCustomerProfileOut(
        id=customer.id,
        phone=mask_phone(customer.phone),
        name=customer.name,
        authenticated=True,
        balance=account.balance,
        plan_name=account.plan_name,
        contract_expiry_date=account.contract_expiry_date,
    )


@router.post("/transactions/{ticket_id}/execute", response_model=AgentTicketOut)
async def execute_agent_transaction(
    ticket_id: int, payload: AgentExecuteRequest, db: DbSession, current: CurrentAgent
) -> AgentTicketOut:
    """坐席引导服务密码复核并单步执行办理工单（US-25，B12 issue #44 AC4）。

    active-chat 右栏待执行办理工单「执行」按钮触发服务密码复核 Modal，坐席引导
    用户再次输入服务密码；校验通过 → Processing → Effective，写审计并推送
    ticket.update / notification.push（客户侧同收）。密码失败 → 401 状态不变。
    返回 AgentTicketOut（坐席视角统一 schema，含脱敏号码与技能组，B14 #55）。
    """
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工单不存在")

    old_status = ticket.status.value
    try:
        execute_ticket_after_agent_reauth(db, ticket, payload.service_password)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"执行失败：{exc}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"执行失败：{exc}"
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
        actor_type="agent",
        actor_id=current.id,
        action="transaction.execute.agent",
        detail={"ticket_id": ticket.id},
    )
    await push_ticket_update(ticket, old_status)
    if notification is not None:
        await push_notification(notification)
    return _agent_ticket_out(db, ticket)


@router.get("/callbacks", response_model=list[CallbackItemOut])
def list_callbacks(db: DbSession, current: CurrentAgent) -> list[CallbackItemOut]:
    """回呼请求工单列表（US-29，PRD queue 页回呼分组）。

    返回 B8 离线兜底创建的回呼请求工单（工单类 + [回呼请求] 前缀 + dispatched），
    供坐席在服务时间联系用户（「拨打」按钮数据源）；号码脱敏（138****0001）。
    """
    return [
        CallbackItemOut(
            ticket_id=entry.ticket.id,
            conversation_id=entry.ticket.conversation_id,
            customer_id=entry.ticket.customer_id,
            customer_phone=entry.customer_phone,
            content=entry.ticket.content,
            skill_group=entry.ticket.skill_group,
            created_at=entry.ticket.created_at,
        )
        for entry in list_callback_tickets(db)
    ]


def _agent_ticket_out(db: Session, ticket: Ticket) -> AgentTicketOut:
    """Ticket → 坐席视角工单（号码经 mask_phone 脱敏，138****0001）。"""
    customer_phone = None
    if ticket.customer_id is not None:
        customer = db.get(Customer, ticket.customer_id)
        if customer is not None:
            customer_phone = mask_phone(customer.phone)
    return AgentTicketOut(
        id=ticket.id,
        conversation_id=ticket.conversation_id,
        ticket_type=ticket.ticket_type.value,
        status=ticket.status.value,
        content=ticket.content,
        skill_group=ticket.skill_group,
        customer_id=ticket.customer_id,
        customer_phone=customer_phone,
        contact_name=ticket.contact_name,
        contact_phone=ticket.contact_phone,
        creator_type=ticket.creator_type,
        creator_id=ticket.creator_id,
        created_at=ticket.created_at,
    )


def _get_agent_ticket_or_404(db: Session, ticket_id: int) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工单不存在")
    return ticket


async def _transition_agent_ticket(
    db: Session,
    ticket: Ticket,
    new_status: str,
    current: User,
    *,
    skill_group: str | None = None,
) -> Ticket:
    """坐席工单状态流转：校验 → 可选技能组 → 通知 → 提交 → WS 推送 → 审计。

    dispatch/close/cancel 共用（US-24）；非法转换抛 ValueError → 422 状态不变。
    """
    old_status = ticket.status.value
    try:
        transition_ticket_status(db, ticket, new_status)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"状态流转失败：{exc}",
        ) from exc
    if skill_group is not None:
        ticket.skill_group = skill_group

    notification: Notification | None = None
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
        actor_type="agent",
        actor_id=current.id,
        action="agent.ticket.status.update",
        detail={"ticket_id": ticket.id, "new_status": ticket.status.value},
    )
    await push_ticket_update(ticket, old_status)
    if notification is not None:
        await push_notification(notification)
    return ticket


@router.get("/tickets", response_model=list[AgentTicketOut])
def list_all_tickets_endpoint(db: DbSession, current: CurrentAgent) -> list[AgentTicketOut]:
    """坐席全局工单列表（US-27，工单管理页数据源）。

    B14（issue #55 AC1）：跨会话汇总全部工单，created_at 倒序（同时间按 id 倒序）；
    号码经 mask_phone 脱敏（138****0001）。当前工单管理页（#22）mock 数据源替换。
    """
    return [_agent_ticket_out(db, entry.ticket) for entry in list_all_tickets(db)]


@router.get("/tickets/{ticket_id}", response_model=AgentTicketOut)
def get_ticket_detail(
    ticket_id: int, db: DbSession, current: CurrentAgent
) -> AgentTicketOut:
    """坐席读工单详情（US-28，工单详情页数据源）。

    B14（issue #55 AC3）：基本信息 + 脱敏号码 + 技能组 + 创建者；不存在 → 404。
    """
    ticket = _get_agent_ticket_or_404(db, ticket_id)
    return _agent_ticket_out(db, ticket)


@router.post("/tickets/{ticket_id}/dispatch", response_model=AgentTicketOut)
async def dispatch_ticket(
    ticket_id: int,
    db: DbSession,
    current: CurrentAgent,
    skill_group: str | None = None,
) -> AgentTicketOut:
    """坐席派单（US-24）：工单类 pending → dispatched（可选技能组，触发通知）。

    B14（issue #55 AC2）：工单管理列表行内「派单」/ 详情页「派单到技能组」共用。
    skill_group 为可选 query 参数（无技能组时仅流转状态）。
    """
    ticket = _get_agent_ticket_or_404(db, ticket_id)
    ticket = await _transition_agent_ticket(
        db, ticket, "dispatched", current, skill_group=skill_group
    )
    return _agent_ticket_out(db, ticket)


@router.post("/tickets/{ticket_id}/close", response_model=AgentTicketOut)
async def close_ticket(
    ticket_id: int, db: DbSession, current: CurrentAgent
) -> AgentTicketOut:
    """坐席关闭（US-24）：工单类 awaiting_confirmation → closed（触发通知）。"""
    ticket = _get_agent_ticket_or_404(db, ticket_id)
    ticket = await _transition_agent_ticket(db, ticket, "closed", current)
    return _agent_ticket_out(db, ticket)


@router.post("/tickets/{ticket_id}/cancel", response_model=AgentTicketOut)
async def cancel_ticket(
    ticket_id: int, db: DbSession, current: CurrentAgent
) -> AgentTicketOut:
    """坐席取消（US-24）：非终态 → cancelled（不触发通知）。"""
    ticket = _get_agent_ticket_or_404(db, ticket_id)
    ticket = await _transition_agent_ticket(db, ticket, "cancelled", current)
    return _agent_ticket_out(db, ticket)
