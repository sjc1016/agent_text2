"""会话领域模型（Conversation / Session / Message）。

PRD/CONTEXT 依据：
  - CONTEXT.md › 会话：Conversation 绑定 User（认证后绑定 Customer），可跨多个 Session
  - CONTEXT.md › 会话片段：Session 一段连续活跃交互，超时断开，重新交互开新 Session
  - CONTEXT.md › 消息：Message 按来源四类（用户/助理/坐席/系统）
  - CONTEXT.md › 会话状态机：Unauthenticated→Authenticated→In-Progress→Handed-off→Closed

本切片（B2 循环1）仅含核心字段与外键关系；状态机流转逻辑在循环6 补全，
Message.source 四类约束在循环3 补全。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MessageSource(str, Enum):
    """消息来源四类（CONTEXT.md › 消息）。

    助理 tool 调用内部记录不属于 Message（不入对话流，仅入审计日志），
    故不在此枚举内——create_message 会拒绝 source=tool。
    """

    USER = "user"
    ASSISTANT = "assistant"
    AGENT = "agent"
    SYSTEM = "system"


class Conversation(Base):
    """会话：一个用户从进入到结束的完整交互序列。

    customer_id 允许 null（访客未认证时也能发起会话，CONTEXT › 会话）；
    认证后回填 Customer 绑定。status 为状态机当前态（循环6 实现流转）。
    agent_id 允许 null：handed_off 后由坐席接入（take_over）回填；
    agent_id 为空即「待接入」（B9 /agents/queues 队列判定，US-20）。
    """

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="unauthenticated")
    handoff_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Session(Base):
    """会话片段：一段连续活跃交互，归属同一 Conversation。

    超时后 ended_at 落位，重新交互开启新 Session（CONTEXT › 会话片段）。
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Message(Base):
    """消息：Conversation 内一条交互记录，按来源四类（循环3 约束）。

    来源（CONTEXT › 消息）：用户/助理/坐席/系统；助理 tool 调用内部记录不入对话流。
    """

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    source: Mapped[MessageSource] = mapped_column(
        SAEnum(MessageSource, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
