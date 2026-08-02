"""工单领域服务（深模块：把 Ticket 创建、查询与双状态机封装在单一接口后）。

PRD 依据：实现决策 › 工单状态机（line 288-292）；实现决策 › API 契约
  /tickets、/tickets/{id}；测试决策 › HTTP 集成 seam；CONTEXT › 工单状态机。

权限边界：客户只能访问 customer_id == 自己的 Ticket；他人工单查询返回 None
（由路由层转 404，避免泄露工单存在性，与会话查询边界一致）。

状态机：按 Ticket.ticket_type 路由到对应合法转换表，非法转换抛 ValueError
（由路由层转 422，状态不变更）。

WS ticket.update / notification.push 推送在 ws 模块（解耦：service 不感知传输层）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, Notification, Ticket
from app.models.ticket import TicketStatus, TicketType

#: 各类型合法状态转换图（PRD line 288-292；CONTEXT › 工单状态机）。
#: 办理类：Pending → Processing → Effective / Failed / Cancelled
#: 工单类：Pending → Dispatched → In-Progress → Awaiting-confirmation → Closed / Cancelled
#: 终态（effective/failed/closed/cancelled）无出边；cancelled 允许从非终态进入。
_TRANSACTION_TRANSITIONS: dict[str, frozenset[str]] = {
    TicketStatus.PENDING.value: frozenset(
        {TicketStatus.PROCESSING.value, TicketStatus.CANCELLED.value}
    ),
    TicketStatus.PROCESSING.value: frozenset(
        {
            TicketStatus.EFFECTIVE.value,
            TicketStatus.FAILED.value,
            TicketStatus.CANCELLED.value,
        }
    ),
    TicketStatus.EFFECTIVE.value: frozenset(),
    TicketStatus.FAILED.value: frozenset(),
    TicketStatus.CANCELLED.value: frozenset(),
}

_TICKETING_TRANSITIONS: dict[str, frozenset[str]] = {
    TicketStatus.PENDING.value: frozenset(
        {TicketStatus.DISPATCHED.value, TicketStatus.CANCELLED.value}
    ),
    TicketStatus.DISPATCHED.value: frozenset(
        {TicketStatus.IN_PROGRESS.value, TicketStatus.CANCELLED.value}
    ),
    TicketStatus.IN_PROGRESS.value: frozenset(
        {TicketStatus.AWAITING_CONFIRMATION.value, TicketStatus.CANCELLED.value}
    ),
    TicketStatus.AWAITING_CONFIRMATION.value: frozenset(
        {TicketStatus.CLOSED.value, TicketStatus.CANCELLED.value}
    ),
    TicketStatus.CLOSED.value: frozenset(),
    TicketStatus.CANCELLED.value: frozenset(),
}

#: 触发 notification.push 站内通知的终态/关键态（CONTEXT › 通知）：
#: 办理类生效/失败、工单类派单/关闭。
_NOTIFICATION_TRIGGERS: dict[str, frozenset[str]] = {
    TicketType.TRANSACTION.value: frozenset(
        {TicketStatus.EFFECTIVE.value, TicketStatus.FAILED.value}
    ),
    TicketType.TICKETING.value: frozenset(
        {TicketStatus.DISPATCHED.value, TicketStatus.CLOSED.value}
    ),
}

#: 触发通知的工单内容模板（CONTEXT › 通知：办理类生效/失败、工单类派单/关闭）。
_NOTIFICATION_MESSAGES: dict[tuple[str, str], str] = {
    (TicketType.TRANSACTION.value, TicketStatus.EFFECTIVE.value): "您的办理工单已生效",
    (TicketType.TRANSACTION.value, TicketStatus.FAILED.value): "您的办理工单已失败",
    (TicketType.TICKETING.value, TicketStatus.DISPATCHED.value): "您的工单已派单",
    (TicketType.TICKETING.value, TicketStatus.CLOSED.value): "您的工单已关闭",
}


def _transitions_for(ticket_type: str) -> dict[str, frozenset[str]]:
    """按工单类型返回合法转换表；未知类型抛 ValueError。"""
    if ticket_type == TicketType.TRANSACTION.value:
        return _TRANSACTION_TRANSITIONS
    if ticket_type == TicketType.TICKETING.value:
        return _TICKETING_TRANSITIONS
    raise ValueError(f"非法工单类型: {ticket_type!r}")


def create_ticket(
    db: Session,
    *,
    conversation_id: int,
    ticket_type: str,
    content: str,
    creator_type: str,
    creator_id: int | None = None,
    customer_id: int | None = None,
    contact_name: str | None = None,
    contact_phone: str | None = None,
) -> Ticket:
    """创建工单，一律以 pending（待执行/待派单）入队。

    CONTEXT › 工单状态机：customer_id 允许 null（Visitor 创建时），仅记录联系方式
    （contact_name + contact_phone）；认证后或坐席补全时回填。
    传入字符串类型而非枚举，便于路由层直接转发 schema 字段；非法类型抛 ValueError
    （由路由层转 422，避免 500）。
    """
    _transitions_for(ticket_type)  # 校验类型合法性（走同表，防漂移）

    ticket = Ticket(
        conversation_id=conversation_id,
        ticket_type=TicketType(ticket_type),
        status=TicketStatus.PENDING,
        content=content,
        customer_id=customer_id,
        contact_name=contact_name,
        contact_phone=contact_phone,
        creator_type=creator_type,
        creator_id=creator_id,
    )
    db.add(ticket)
    db.flush()
    return ticket


def list_tickets_for_customer(db: Session, customer: Customer) -> list[Ticket]:
    """返回当前客户的工单列表（仅自己的，按 id 升序）。"""
    stmt = select(Ticket).where(Ticket.customer_id == customer.id).order_by(Ticket.id)
    return list(db.execute(stmt).scalars().all())


def get_customer_ticket_or_none(db: Session, customer: Customer, ticket_id: int) -> Ticket | None:
    """取当前客户的工单；不存在或不属于该客户 → None（路由层转 404）。"""
    ticket = db.get(Ticket, ticket_id)
    if ticket is None or ticket.customer_id != customer.id:
        return None
    return ticket


def transition_ticket_status(db: Session, ticket: Ticket, new_status: str) -> Ticket:
    """按工单类型状态机校验并流转工单状态。

    合法转换 → 更新 ticket.status 并返回 ticket（调用方负责 commit 与 WS 推送）；
    非法转换 / 未知状态 / 同态转换 → 抛 ValueError（由路由层转 422，状态不变更）。

    WS ticket.update / notification.push 推送在 ws 模块（解耦：service 不感知传输层）。
    """
    transitions = _transitions_for(ticket.ticket_type.value)

    if new_status not in {member.value for member in TicketStatus}:
        raise ValueError(f"非法工单状态: {new_status!r}")
    if new_status == ticket.status.value:
        raise ValueError(f"同态转换无意义: {new_status!r}")

    allowed = transitions.get(ticket.status.value, frozenset())
    if new_status not in allowed:
        raise ValueError(
            f"非法状态转换: {ticket.ticket_type.value} {ticket.status.value!r} → {new_status!r}"
        )

    ticket.status = TicketStatus(new_status)
    db.flush()
    return ticket


def should_push_notification(ticket: Ticket, new_status: str) -> bool:
    """该状态是否触发站内通知（CONTEXT › 通知：办理生效/失败、工单派单/关闭）。"""
    triggers = _NOTIFICATION_TRIGGERS.get(ticket.ticket_type.value, frozenset())
    return new_status in triggers


def notification_message(ticket: Ticket, new_status: str) -> str:
    """触发通知时的站内文案（按类型+状态取模板）。"""
    return _NOTIFICATION_MESSAGES.get((ticket.ticket_type.value, new_status), "您的工单状态已更新")


def create_notification(db: Session, ticket: Ticket, message: str) -> Notification:
    """创建一条站内通知（CONTEXT › 通知：Ticket 状态变化的站内消息）。

    customer_id 透传 Ticket 关联客户（Visitor 工单为 None 时仅落库不推送）。
    """
    notification = Notification(
        ticket_id=ticket.id,
        customer_id=ticket.customer_id,
        message=message,
    )
    db.add(notification)
    db.flush()
    return notification
