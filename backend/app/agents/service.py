"""坐席业务逻辑（深模块：认证判定与队列查询封装在服务层）。

PRD 依据：
  - 实现决策 › API 契约 /agents/login（工号+密码认证）
  - 实现决策 › API 契约 /agents/queues（待接入队列 = Handed-off 未接入会话）
  - 测试决策 › HTTP 集成 seam（坐席登录与队列）
  - 用户故事 US-19/20
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import verify_password
from app.models import Conversation, Customer, Message, Ticket, User
from app.models.conversation import MessageSource
from app.models.inquiry import CustomerAccount
from app.models.ticket import TicketStatus, TicketType

#: 坐席状态三态（US-30；schema 侧用 Literal 镜像，运行时 WS 校验复用本集合）。
AGENT_STATUSES: frozenset[str] = frozenset({"online", "offline", "break"})


def authenticate_agent(db: Session, employee_id: str, password: str) -> User | None:
    """工号 + 密码认证；通过返回坐席账号 User，失败返回 None。"""
    agent = db.execute(select(User).where(User.employee_id == employee_id)).scalar_one_or_none()
    if agent is None:
        return None
    if not verify_password(password, agent.password_hash):
        return None
    return agent


def mask_phone(phone: str) -> str:
    """号码脱敏：138****0001（客户隐私，CONTEXT › 审计日志 › 用户敏感数据）。"""
    if len(phone) < 7:
        return phone
    return f"{phone[:3]}****{phone[-4:]}"


@dataclass
class QueueEntry:
    """待接入队列项（conversation + 展示增强字段）。"""

    conversation: Conversation
    customer_phone: str | None
    last_user_message: str | None


def get_agent_conversation_or_none(db: Session, conversation_id: int) -> Conversation | None:
    """取坐席可见的转接会话；不存在或非 handed_off → None（路由层转 404）。

    B12（issue #44 AC1，US-21）：坐席接入会话后读取对话流，仅 handed_off
    转接中的会话对坐席可见（转回助理后不可读，不泄露客户会话存在性）。
    """
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.status != "handed_off":
        return None
    return conv


def get_customer_profile(db: Session, customer_id: int) -> tuple[Customer, CustomerAccount] | None:
    """取客户资料 + 账户快照；Customer 或 CustomerAccount 任一缺失 → None。

    B12（issue #44 AC2，US-21）：坐席查看 active-chat 右栏客户资料（号码脱敏、
    名称、认证态）+ 账户信息（余额/套餐名/合约到期，复用 inquiry 数据源）。
    访客（无 Customer）或未建账户（无 CustomerAccount）均视为不可查 → 404。
    """
    customer = db.get(Customer, customer_id)
    if customer is None:
        return None
    account = db.execute(
        select(CustomerAccount).where(CustomerAccount.customer_id == customer_id)
    ).scalar_one_or_none()
    if account is None:
        return None
    return customer, account


def list_conversation_tickets(db: Session, conversation_id: int) -> list[Ticket]:
    """返回会话所属工单列表（US-23，按 id 升序）。"""
    stmt = select(Ticket).where(Ticket.conversation_id == conversation_id).order_by(Ticket.id)
    return list(db.execute(stmt).scalars().all())


def execute_ticket_after_agent_reauth(db: Session, ticket: Ticket, service_password: str) -> Ticket:
    """坐席引导服务密码复核并单步执行办理工单（US-25，B12 issue #44 AC4）。

    方案 A（triage 确认）：单步复核执行——请求携带 service_password，对工单所属
    客户 verify_password 校验通过后按既有执行链路（Processing → Effective）执行。

    Raises:
        ValueError: 工单非办理类 / 非 pending（执行可行性，路由层转 422）
        PermissionError: 访客工单或服务密码校验失败（路由层转 401，状态不变更）
    调用方负责 commit 与 WS 推送（ticket.update + notification.push）与审计。
    """
    from app.transaction.service import assert_executable_transaction, execute_transaction

    assert_executable_transaction(ticket)
    if ticket.customer_id is None:
        raise PermissionError("访客工单无法引导服务密码复核")
    customer = db.get(Customer, ticket.customer_id)
    if customer is None or not verify_password(service_password, customer.service_password_hash):
        raise PermissionError("服务密码校验失败")
    return execute_transaction(db, ticket)


def list_pending_queue_entries(db: Session) -> list[QueueEntry]:
    """返回待接入队列：Handed-off 状态且尚未被坐席接入的会话，按创建时间升序。

    US-20：坐席查看待接入会话队列；「待接入」= 已 Handoff（handed_off）且
    agent_id 为空（未被任何坐席接入）的会话。
    """
    convs = (
        db.execute(
            select(Conversation)
            .where(Conversation.status == "handed_off", Conversation.agent_id.is_(None))
            .order_by(Conversation.created_at)
        )
        .scalars()
        .all()
    )

    entries: list[QueueEntry] = []
    for conv in convs:
        customer_phone = None
        if conv.customer_id is not None:
            customer = db.get(Customer, conv.customer_id)
            if customer is not None:
                customer_phone = mask_phone(customer.phone)

        last_msg = db.execute(
            select(Message)
            .where(
                Message.conversation_id == conv.id,
                Message.source == MessageSource.USER,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        ).scalar_one_or_none()

        entries.append(
            QueueEntry(
                conversation=conv,
                customer_phone=customer_phone,
                last_user_message=last_msg.content if last_msg is not None else None,
            )
        )
    return entries


@dataclass
class CallbackTicketEntry:
    """回呼请求工单项（ticket + 展示增强字段）。"""

    ticket: Ticket
    customer_phone: str | None


def list_callback_tickets(db: Session) -> list[CallbackTicketEntry]:
    """返回回呼请求工单列表（US-29），按创建时间升序。

    回呼请求工单 = B8 离线兜底产物（CONTEXT › 离线兜底）：工单类 + 内容前缀
    [回呼请求] + 创建即派单（dispatched）+ skill_group。PRD queue 页要求
    底部独立「回呼请求」分组（拨打按钮），本端点提供该分组数据源。
    """
    from app.handoff.service import CALLBACK_TICKET_CONTENT_PREFIX

    tickets = (
        db.execute(
            select(Ticket)
            .where(
                Ticket.ticket_type == TicketType.TICKETING,
                Ticket.status == TicketStatus.DISPATCHED,
                Ticket.content.like(f"{CALLBACK_TICKET_CONTENT_PREFIX}%"),
            )
            .order_by(Ticket.created_at)
        )
        .scalars()
        .all()
    )

    entries: list[CallbackTicketEntry] = []
    for ticket in tickets:
        customer_phone = None
        if ticket.customer_id is not None:
            customer = db.get(Customer, ticket.customer_id)
            if customer is not None:
                customer_phone = mask_phone(customer.phone)
        entries.append(CallbackTicketEntry(ticket=ticket, customer_phone=customer_phone))
    return entries
