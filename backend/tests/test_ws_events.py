"""F0 循环5：WS 事件契约镜像（后端侧）。

验收标准（issue #2 / PRD 第282行）：
  backend/app/ws/events.py 镜像 frontend/shared/events.ts 的事件名集合，
  含 PRD 定义的全部事件名。双边一致性由 test_ws_event_contract.py 校验。

本测试只断言后端镜像自身的正确性：事件名清单完整、值与 PRD 一致、无重复。
"""

from app.ws.events import EVENT_NAMES, WsEventName

EXPECTED_EVENT_NAMES = [
    "llm.token",
    "message.new",
    "handoff.start",
    "handoff.end",
    "ticket.update",
    "notification.push",
    "system.message",
    "agent.status",
    "conversation.state",
    "second.confirm",
    "reauth.required",
]


def test_event_names_contains_all_prd_events():
    assert set(EVENT_NAMES) == set(EXPECTED_EVENT_NAMES)


def test_event_names_have_no_duplicates():
    event_list = list(EVENT_NAMES)
    assert len(event_list) == len(set(event_list))


def test_ws_event_name_enum_values_match_prd():
    assert {member.value for member in WsEventName} == set(EXPECTED_EVENT_NAMES)
