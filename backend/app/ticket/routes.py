"""工单 REST 路由。

B7（issue #10）：
  POST /tickets — 创建工单（办理类/工单类，customer 取当前认证客户）
  GET /tickets — 当前客户工单列表
  GET /tickets/{id} — 工单详情（他人工单 → 404，不泄露存在性）
  PATCH /tickets/{id} — 状态流转（双状态机校验，非法 → 422）

鉴权复用 B1 的 CurrentCustomer（Authorization header Bearer）。
PRD 依据：实现决策 › API 契约 / RESTful 端点（/tickets、/tickets/{id}）；
  实现决策 › 工单状态机；测试决策 › HTTP 集成 seam；US-13, US-14, US-23, US-24。

状态流转成功后推送 WS ticket.update；触发通知态（办理生效/失败、工单派单/关闭）
推送 notification.push 站内通知（ws 模块推送，服务层不感知传输层）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentCustomer
from app.db import get_db
from app.models import Notification, Ticket
from app.ticket.schemas import TicketCreate, TicketOut, TicketStatusUpdate
from app.ticket.service import (
    create_notification,
    create_ticket,
    get_customer_ticket_or_none,
    list_tickets_for_customer,
    notification_message,
    should_push_notification,
    transition_ticket_status,
)
from app.ws.hub import push_notification, push_ticket_update

router = APIRouter(prefix="/tickets", tags=["ticket"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def create(current: CurrentCustomer, payload: TicketCreate, db: DbSession) -> Ticket:
    """创建工单（办理类/工单类），customer 关联当前认证客户，默认 pending 入队。"""
    ticket = create_ticket(
        db,
        conversation_id=payload.conversation_id,
        ticket_type=payload.ticket_type,
        content=payload.content,
        creator_type="customer",
        creator_id=current.id,
        customer_id=current.id,
    )
    db.commit()
    db.refresh(ticket)
    return ticket


@router.get("", response_model=list[TicketOut])
def list_tickets(current: CurrentCustomer, db: DbSession) -> list[Ticket]:
    """当前客户的工单列表（未认证 401 由 CurrentCustomer 守卫）。"""
    return list_tickets_for_customer(db, current)


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: int, current: CurrentCustomer, db: DbSession) -> Ticket:
    """工单详情；不存在或不属于当前客户 → 404（不泄露存在性）。"""
    ticket = get_customer_ticket_or_none(db, current, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工单不存在")
    return ticket


@router.patch("/{ticket_id}", response_model=TicketOut)
async def update_status(
    ticket_id: int, payload: TicketStatusUpdate, current: CurrentCustomer, db: DbSession
) -> Ticket:
    """工单状态流转：按 ticket_type 双状态机校验，非法 → 422 状态不变。

    成功后推送 WS ticket.update；触发通知态（办理生效/失败、工单派单/关闭）
    推送 notification.push 站内通知。
    """
    ticket = get_customer_ticket_or_none(db, current, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工单不存在")

    old_status = ticket.status.value
    try:
        transition_ticket_status(db, ticket, payload.status)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"状态流转失败：{exc}",
        ) from exc

    notification: Notification | None = None
    if should_push_notification(ticket, ticket.status.value):
        notification = create_notification(
            db, ticket, notification_message(ticket, ticket.status.value)
        )

    db.commit()
    db.refresh(ticket)
    if notification is not None:
        db.refresh(notification)
    # WS 推送在提交后执行（payload 取库中最新状态）
    await push_ticket_update(ticket, old_status)
    if notification is not None:
        await push_notification(notification)
    return ticket
