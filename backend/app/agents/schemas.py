"""坐席请求/响应 schema（Pydantic）。

PRD 依据：实现决策 › API 契约 /agents/login、/agents/status、/agents/queues
（OpenAPI 自动生成）；用户故事 US-19/20/30。
"""

from __future__ import annotations

from datetime import date, datetime
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


class AgentExecuteRequest(BaseModel):
    """坐席引导办理执行请求（US-25，B12 issue #44 AC4）。

    单步复核执行：坐席在 active-chat 右栏「执行」触发服务密码复核 Modal，
    引导用户再次输入服务密码（PRD › 办理执行复核，单因素认证补偿控制）。
    """

    service_password: str = Field(..., description="服务密码（坐席引导客户再次输入）")


class AgentCustomerProfileOut(BaseModel):
    """坐席视角客户资料 + 账户信息（US-21，active-chat 右栏客户标识卡 + 账户信息块）。

    号码脱敏（138****0001，CONTEXT › 审计日志 › 用户敏感数据）；authenticated 恒为
    True（Customer 存在即已认证主体）；账户字段复用 inquiry 数据源 CustomerAccount
    （余额/套餐名/合约到期）。访客（无 Customer）或未建账户 → 404（不编造）。
    """

    id: int
    phone: str  # 脱敏（138****0001）
    name: str | None
    authenticated: bool
    balance: float
    plan_name: str | None
    contract_expiry_date: date | None


class ConversationViewOut(BaseModel):
    """坐席视角单会话视图（US-21，active-chat 页会话上下文）。

    仅 handed_off 转接中的会话可见（复用消息历史可见性规则，否则 404）；
    customer_phone 经 mask_phone 脱敏（138****0001）；handoff_reason 为
    转接原因（explicit_request / out_of_scope 等，PRD queue 页 Caption 同源）。
    """

    conversation_id: int
    status: str
    customer_id: int | None
    customer_phone: str | None  # 脱敏（138****0001）
    handoff_reason: str | None  # 转接原因
    created_at: datetime


class AgentTicketOut(BaseModel):
    """坐席视角工单（列表/详情项，US-27/28）：TicketOut 字段 + 脱敏号码 + 技能组。

    customer_phone 经 mask_phone 脱敏（138****0001）；skill_group 记录派单目标技能组。
    """

    id: int
    conversation_id: int
    ticket_type: str
    status: str
    content: str
    skill_group: str | None
    customer_id: int | None
    customer_phone: str | None  # 脱敏（138****0001）
    contact_name: str | None
    contact_phone: str | None
    creator_type: str
    creator_id: int | None
    created_at: datetime
