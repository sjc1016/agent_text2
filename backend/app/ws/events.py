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
"""

from enum import Enum


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
