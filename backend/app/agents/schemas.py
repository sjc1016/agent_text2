"""坐席请求/响应 schema（Pydantic）。

PRD 依据：实现决策 › API 契约 /agents/login、/agents/status、/agents/queues
（OpenAPI 自动生成）；用户故事 US-19/20/30。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: 坐席状态三态（US-30 / PRD agent-console app-shell：在线/小休/离线）。
AgentStatus = Literal["online", "offline", "break"]


class AgentLoginRequest(BaseModel):
    employee_id: str = Field(..., description="坐席工号")
    password: str = Field(..., description="登录密码")


class AgentPublic(BaseModel):
    """坐席公开档案（/agents/status 响应；不暴露 password_hash）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: str
    name: str
    status: str


class AgentStatusUpdate(BaseModel):
    status: AgentStatus = Field(..., description="在线/离线/小休")


class QueueItemOut(BaseModel):
    """待接入队列项：一条 Handed-off 待接入会话（US-20）。"""

    conversation_id: int
    status: str
    created_at: datetime
    customer_id: int | None
    customer_phone: str | None  # 脱敏（138****0001）
    last_user_message: str | None  # 会话起因摘要（最后一条用户消息）
    reason: str | None  # 转接原因（Conversation.handoff_reason，PRD queue 页 Caption）


class CallbackItemOut(BaseModel):
    """回呼请求工单项：离线兜底创建的 [回呼请求] Ticket（US-29，PRD queue 页回呼分组）。"""

    ticket_id: int
    conversation_id: int
    customer_id: int | None
    customer_phone: str | None  # 脱敏（138****0001）
    content: str  # 含 [回呼请求] 前缀（B8 离线兜底内容模板）
    skill_group: str | None  # 派单技能组（套餐业务组/故障报修组/投诉处理组）
    created_at: datetime
