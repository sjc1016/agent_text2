"""工单领域模型（Ticket / Notification）。

PRD/CONTEXT 依据：
  - CONTEXT.md › 工单状态机：统一 Ticket 模型（ID、所属 Conversation、创建者、
    类型、内容、创建时间、状态、关联 Customer 允许 null）
  - CONTEXT.md › 通知：Ticket 状态变化时推送的站内消息（对话内推送）
  - PRD line 288-292：办理类 Pending→Processing→Effective/Failed/Cancelled；
    工单类 Pending→Dispatched→In-Progress→Awaiting-confirmation→Closed/Cancelled

本切片（B7）仅含核心字段与枚举；状态机流转逻辑在 service 层（transition_ticket_status）。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TicketType(str, Enum):
    """工单类型（CONTEXT › 业务能力：办理类 / 工单类）。"""

    TRANSACTION = "transaction"
    TICKETING = "ticketing"


class TicketStatus(str, Enum):
    """工单状态（PRD line 288-292，两状态机状态并集）。

    - 办理类：pending → processing → effective / failed / cancelled
    - 工单类：pending → dispatched → in_progress → awaiting_confirmation → closed / cancelled
    各类型合法转换由 service.transition_ticket_status 依据类型路由。
    """

    PENDING = "pending"
    PROCESSING = "processing"
    EFFECTIVE = "effective"
    FAILED = "failed"
    DISPATCHED = "dispatched"
    IN_PROGRESS = "in_progress"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class Ticket(Base):
    """工单：需要后续跟踪的业务事项（办理、投诉、报修等）。

    CONTEXT › 工单状态机：
      - customer_id 允许 null（Visitor 创建时），仅记录联系方式（contact_name+contact_phone）；
        认证后或坐席补全时回填。
      - 一个 Conversation 可并存多个 Ticket。
    creator_type 表达创建者形态（customer/agent/assistant），creator_id 关联对应主体。
    skill_group 记录派单目标技能组（套餐业务组/故障报修组/投诉处理组）；回呼请求
    Ticket（B8 离线兜底）创建即派单到此字段标注的组（CONTEXT › 离线兜底）。
    """

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    ticket_type: Mapped[TicketType] = mapped_column(
        SAEnum(TicketType, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    status: Mapped[TicketStatus] = mapped_column(
        SAEnum(TicketStatus, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=TicketStatus.PENDING.value,
    )
    content: Mapped[str] = mapped_column(String, nullable=False)
    skill_group: Mapped[str | None] = mapped_column(String, nullable=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String, nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    creator_type: Mapped[str] = mapped_column(String, nullable=False)
    creator_id: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Notification(Base):
    """通知：Ticket 状态变化时推送给用户的站内消息（对话内推送）。

    CONTEXT › 通知：
      - 办理类 Ticket：生效/失败时通知
      - 工单类 Ticket：派单/关闭时通知
    customer_id 允许 null（Visitor 场景无客户主体，仅站内推送目标缺失时不落客户）。
    read 标记未读/已读，供 UI-C-4 通知预览条消费。
    """

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    message: Mapped[str] = mapped_column(String, nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
