"""工单请求/响应 schema（Pydantic）。

PRD 依据：API 契约 /tickets、/tickets/{id}（OpenAPI 自动生成）。
ORM → Pydantic 转换经 from_attributes 开启（SQLAlchemy 2.0 模型直出）。
ticket_type / status 为字符串透传（服务层校验枚举合法性，路由层转 422）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TicketTypeField = Literal["transaction", "ticketing"]


class TicketCreate(BaseModel):
    """创建工单请求（REST 客户侧；customer 自动取当前认证客户）。"""

    conversation_id: int = Field(..., description="所属会话")
    ticket_type: TicketTypeField = Field(..., description="工单类型：transaction/ticketing")
    content: str = Field(..., description="工单内容（办理事项描述 / 报修描述）")


class TicketStatusUpdate(BaseModel):
    """状态流转请求（PATCH /tickets/{id}，按工单类型状态机校验）。"""

    status: str = Field(..., description="目标状态（两状态机合法状态名）")


class TicketOut(BaseModel):
    """工单详情/列表项。customer 关联允许 null（Visitor 创建时仅联系方式）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    ticket_type: str
    status: str
    content: str
    customer_id: int | None
    contact_name: str | None
    contact_phone: str | None
    creator_type: str
    creator_id: int | None
    created_at: datetime
