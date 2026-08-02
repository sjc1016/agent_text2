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
from app.models import Conversation, Customer, Message, User
from app.models.conversation import MessageSource

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
