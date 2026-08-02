"""会话与消息的请求/响应 schema（Pydantic）。

PRD 依据：API 契约 /conversations、/conversations/{id}/messages（OpenAPI 自动生成）。
ORM → Pydantic 转换经 from_attributes 开启（SQLAlchemy 2.0 模型直出）。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConversationOut(BaseModel):
    """会话列表项。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int | None
    status: str
    created_at: datetime


class MessageOut(BaseModel):
    """消息历史项。source 四类分类由循环3 约束，此处仅透传。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    source: str
    content: str
    created_at: datetime
