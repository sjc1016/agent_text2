"""会话与消息查询服务（深模块：把查询与权限边界封装在单一接口后）。

PRD 依据：实现决策 › API 契约 / RESTful 端点；测试决策 › HTTP 集成 seam；
  实现决策 › 会话状态机（line 286）。

权限边界：客户只能访问 customer_id == 自己的 Conversation；他人会话查询返回 None
（由路由层转 404，避免泄露会话存在性）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, Customer, Message
from app.models.conversation import MessageSource

#: 会话状态机全部合法状态名（PRD line 286）。
CONVERSATION_STATES: frozenset[str] = frozenset(
    {"unauthenticated", "authenticated", "in_progress", "handed_off", "closed"}
)

#: 合法状态转换图（PRD line 286）。
#: Unauthenticated → Authenticated → In-Progress（等待二次确认）
#:                               → Authenticated（Ticket 入队后回退）
#:                               → Handed-off（转接）→ Closed
#: handed_off → authenticated：坐席转回助理（US-26，B9）；closed 为终态。
#: 任意活跃态可 → closed（会话异常/正常关闭）。
_CONVERSATION_TRANSITIONS: dict[str, frozenset[str]] = {
    "unauthenticated": frozenset({"authenticated", "closed"}),
    "authenticated": frozenset({"in_progress", "handed_off", "closed"}),
    "in_progress": frozenset({"authenticated", "closed"}),
    "handed_off": frozenset({"authenticated", "closed"}),
    "closed": frozenset(),
}


def list_conversations_for_customer(db: Session, customer: Customer) -> list[Conversation]:
    """返回当前客户的会话列表（仅自己的，按 id 升序）。"""
    stmt = select(Conversation).where(Conversation.customer_id == customer.id)
    return list(db.execute(stmt).scalars().all())


def create_conversation(db: Session, customer: Customer) -> Conversation:
    """为认证客户创建一个新会话（status=authenticated，PRD line 286）。

    #24 UI-C-3 集成切片：对话页首次进入需要会话承载消息流（US-1 / US-18）。
    会话由客户发起（认证即 authenticated）；访客会话（customer_id=None）由后续
    Visitor 流程另行支持，本切片不引入。
    """
    conv = Conversation(customer_id=customer.id, status="authenticated")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def get_customer_conversation_or_none(
    db: Session, customer: Customer, conversation_id: int
) -> Conversation | None:
    """取当前客户的会话；不存在或不属于该客户 → None（路由层转 404）。"""
    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.customer_id != customer.id:
        return None
    return conv


def list_messages_for_conversation(db: Session, conversation_id: int) -> list[Message]:
    """返回会话消息历史，按 created_at 升序（消息历史顺序）。"""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(db.execute(stmt).scalars().all())


def create_message(db: Session, conversation_id: int, source: str, content: str) -> Message:
    """创建一条消息，并强制 source ∈ 四类合法来源。

    CONTEXT › 消息：Message 仅四类来源——user/assistant/agent/system；
    助理调用 tools 的内部记录不属于 Message（不入对话流，仅入审计日志），
    因此 source="tool" 与任何非四类值均在此守卫拒绝。

    传入字符串而非枚举，便于路由层直接转发 schema 字段；非法值抛 ValueError
    （由路由层转 422，避免 500）。
    """
    try:
        typed_source = MessageSource(source)
    except ValueError as e:
        raise ValueError(f"非法 Message source: {source!r}") from e

    msg = Message(
        conversation_id=conversation_id,
        source=typed_source,
        content=content,
    )
    db.add(msg)
    db.flush()
    return msg


def transition_conversation_state(db: Session, conv: Conversation, new_state: str) -> Conversation:
    """按 PRD line 286 状态机校验并流转会话状态。

    合法转换 → 更新 conv.status 并返回 conv（调用方负责 commit 与 WS 推送）；
    非法转换 / 未知状态 / 同态转换 → 抛 ValueError（由调用方转 system.message 提示，
    状态不变更）。

    WS conversation.state 事件推送在 ws 模块（解耦：service 不感知传输层）。
    """
    if new_state not in CONVERSATION_STATES:
        raise ValueError(f"非法会话状态: {new_state!r}")
    if new_state == conv.status:
        raise ValueError(f"同态转换无意义: {new_state!r}")

    allowed = _CONVERSATION_TRANSITIONS.get(conv.status, frozenset())
    if new_state not in allowed:
        raise ValueError(f"非法状态转换: {conv.status!r} → {new_state!r}")

    conv.status = new_state
    db.flush()
    return conv
