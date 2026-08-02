"""WS 事件契约镜像（后端侧）。

F0 循环5（issue #2 / PRD 第282行）：
  本模块镜像 frontend/shared/events.ts 的事件名集合，作为后端发送/接收 WS 事件的
  事件名权威来源。双边事件名一致性由 scripts/check_ws_events.py（CI 调用）+
  tests/test_ws_event_contract.py（契约测试）校验。

设计约定：
  - 事件名 SSOT 为 `WsEventName` 枚举，成员值与 PRD 第282行 / 前端 WS_EVENT_NAMES
    逐字一致。
  - `EVENT_NAMES` 由枚举派生的 frozenset，供契约校验与运行时校验入站事件名复用。
  - 各事件 payload 的 Pydantic 模型由对应业务垂直切片在本模块内补全
    （与前端 WsEventPayloadMap 细化同步），events.py 始终是文件级 SSOT。
  - envelope 统一为 {event, data}；payload 字段沿用 snake_case（与前端约定，
    避免跨语言映射层）。

B2 循环5（issue #7 验收3）：补全 message.new / system.message 的 payload 模型。
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class WsEventName(str, Enum):
    """WS 事件名枚举。成员值与 frontend/shared/events.ts 的 WS_EVENT_NAMES 逐字一致。"""

    LLM_TOKEN = "llm.token"
    MESSAGE_NEW = "message.new"
    HANDOFF_START = "handoff.start"
    HANDOFF_END = "handoff.end"
    TICKET_UPDATE = "ticket.update"
    NOTIFICATION_PUSH = "notification.push"
    SYSTEM_MESSAGE = "system.message"
    AGENT_STATUS = "agent.status"
    CONVERSATION_STATE = "conversation.state"
    SECOND_CONFIRM = "second.confirm"
    REAUTH_REQUIRED = "reauth.required"


#: 全部 WS 事件名集合，由枚举派生，禁止手写以防与枚举漂移。
EVENT_NAMES: frozenset[str] = frozenset(member.value for member in WsEventName)


class MessageNewPayload(BaseModel):
    """message.new 事件 payload（与 REST MessageOut 字段镜像，snake_case）。

    持久化的新 Message 入对话流时推送；source ∈ user/assistant/agent/system
    （CONTEXT › 消息 四类来源）。前端可复用 MessageOut 类型消费本 payload。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    source: str
    content: str
    created_at: datetime


class SystemMessagePayload(BaseModel):
    """system.message 事件 payload（瞬时系统动作提示，不持久化为 Message）。

    用于会话建立提示、无权限提示、坐席状态变更等系统动作反馈；
    与 message.new（持久化消息）互补，不进对话历史。
    """

    content: str
    created_at: datetime


class ConversationStatePayload(BaseModel):
    """conversation.state 事件 payload（会话状态机流转通知）。

    PRD line 286 状态机：unauthenticated → authenticated → in_progress
    → authenticated(回退) → handed_off → closed。每次合法流转推送本事件。
    """

    conversation_id: int
    old_state: str
    new_state: str
    changed_at: datetime


class TicketUpdatePayload(BaseModel):
    """ticket.update 事件 payload（工单状态变化通知，PRD line 282）。

    每次合法状态流转推送；old_status 供前端做状态差量展示
    （与 REST TicketOut 状态字段镜像，snake_case）。
    """

    id: int
    conversation_id: int
    ticket_type: str
    status: str
    old_status: str
    changed_at: datetime


class NotificationPushPayload(BaseModel):
    """notification.push 事件 payload（站内通知，PRD line 282）。

    触发态：办理类生效/失败、工单类派单/关闭（CONTEXT › 通知）；
    read 标记未读/已读，供 UI-C-4 通知预览条消费。
    """

    id: int
    ticket_id: int
    message: str
    read: bool
    created_at: datetime


class AgentStatusPayload(BaseModel):
    """agent.status 事件 payload（坐席状态变更通知，PRD line 282；US-30）。

    坐席切换在线/离线/小休时经 WS 推送；status ∈ online/offline/break
    （与前端 AgentStatus 三态镜像）。
    """

    agent_id: int
    status: str
    changed_at: datetime


class SecondConfirmPayload(BaseModel):
    """second.confirm 事件 payload（办理二次确认请求，PRD line 282；US-8~US-11）。

    办理类 tool/REST 发起后推送，含结构化业务影响（套餐对比/生效时间/合约影响/费用变化），
    前端据此渲染二次确认 Modal；会话同步进入 in_progress（等待二次确认）。
    """

    conversation_id: int
    transaction_type: str
    business_impact: dict  # BusinessImpact 字段快照（snake_case，前端直接消费）
    requested_at: datetime


class ReauthRequiredPayload(BaseModel):
    """reauth.required 事件 payload（办理执行前服务密码复核请求，PRD line 282；US-12）。

    办理类 Ticket 从「待执行」进入「执行中」前由调度任务推送，要求用户再次输入服务密码
    （/auth/reauth）作为单因素认证的补偿控制；复核通过后颁发 execute_token 方可执行。
    """

    ticket_id: int
    conversation_id: int
    message: str
    requested_at: datetime
