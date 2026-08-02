"""WS 事件契约镜像 + 推送测试。

F0 循环5（issue #2）：后端事件名镜像自身正确性（清单完整 / 无重复 / 枚举值匹配）。
B2 循环5（issue #7 验收3）：推送 message.new + system.message + payload 镜像。
B2 循环6（issue #7 验收4）：推送 conversation.state + payload 镜像。

验收标准（issue #7）：
  新消息推送 message.new，系统动作推送 system.message
  （PRD 依据：实现决策 › API 契约 / WebSocket 事件；
              测试决策 › WS 事件 seam；用户故事 US-1）

事件分工（与 CONTEXT › 消息 对齐）：
  - message.new：持久化的新 Message（user/assistant/agent/system 四类来源）入对话流
  - system.message：瞬时系统动作提示（不持久化为 Message，如「会话已建立」）

envelope 格式（frontend/shared/events.ts SSOT）：{ event, data }，payload snake_case。
双边事件名一致性由 test_ws_event_contract.py 校验；本文件只断言后端镜像自身 + 推送行为。
"""

from __future__ import annotations

import bcrypt
import pytest

from app.ws.events import EVENT_NAMES, WsEventName

#: PRD 第282行定义的全部 WS 事件名（与前端 WS_EVENT_NAMES 逐字一致）。
_EXPECTED_EVENT_NAMES = [
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
    """后端事件名集合与 PRD 第282行清单逐字一致。"""
    assert set(EVENT_NAMES) == set(_EXPECTED_EVENT_NAMES)


def test_event_names_have_no_duplicates():
    """事件名集合无重复（frozenset 天然去重，本测试守卫 SSOT 源头）。"""
    event_list = list(EVENT_NAMES)
    assert len(event_list) == len(set(event_list))


def test_ws_event_name_enum_values_match_prd():
    """WsEventName 枚举值与 PRD 第282行清单一致。"""
    assert {member.value for member in WsEventName} == set(_EXPECTED_EVENT_NAMES)


# --- B2 循环5/6：WS 推送行为测试（鉴权 / message.new / system.message / conversation.state） ---

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_customer(db, phone: str = "13900000030", password: str = "svc12345"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password(password))
    db.add(customer)
    db.commit()
    return customer


def test_ws_pushes_system_message_on_accept(ws_client, db):
    """accept 后立即推 system.message（系统动作：会话已建立）。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db, phone="13900000031")
    token = create_access_token(customer.id)

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        event = ws.receive_json()

    assert event["event"] == "system.message"
    payload = event["data"]
    assert isinstance(payload["content"], str) and payload["content"]
    assert isinstance(payload["created_at"], str)  # ISO 字符串


def test_ws_message_new_on_client_message(ws_client, db):
    """客户端发消息 → 服务端持久化 user 消息并推 message.new。"""
    from app.auth.security import create_access_token
    from app.models import Conversation

    customer = _create_customer(db, phone="13900000032")
    token = create_access_token(customer.id)
    conv = Conversation(customer_id=customer.id, status="authenticated")
    db.add(conv)
    db.commit()

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # 消费 accept 后的 system.message
        ws.send_json({"type": "message", "conversation_id": conv.id, "content": "你好"})
        event = ws.receive_json()

    assert event["event"] == "message.new"
    payload = event["data"]
    # payload 字段与 REST MessageOut 镜像（snake_case）
    assert payload["conversation_id"] == conv.id
    assert payload["source"] == "user"
    assert payload["content"] == "你好"
    assert isinstance(payload["id"], int)
    assert isinstance(payload["created_at"], str)


def test_ws_message_new_persists_message(ws_client, db):
    """客户端发消息后，DB 中持久化该 user 消息（入对话流）。"""
    from sqlalchemy import select

    from app.auth.security import create_access_token
    from app.models import Conversation, Message

    customer = _create_customer(db, phone="13900000033")
    token = create_access_token(customer.id)
    conv = Conversation(customer_id=customer.id, status="authenticated")
    db.add(conv)
    db.commit()

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.message
        ws.send_json({"type": "message", "conversation_id": conv.id, "content": "持久化测试"})
        ws.receive_json()  # message.new

    msgs = list(db.execute(select(Message).where(Message.conversation_id == conv.id)).scalars())
    assert len(msgs) == 1
    assert msgs[0].source == "user"
    assert msgs[0].content == "持久化测试"


def test_ws_message_new_rejects_other_customer_conversation(ws_client, db):
    """客户端发他人会话的消息 → 不持久化、不推 message.new，改推 system.message 错误提示。

    权限边界与 REST list_messages 一致（不泄露他人会话存在性）。
    """
    from sqlalchemy import select

    from app.auth.security import create_access_token
    from app.models import Conversation, Message

    customer = _create_customer(db, phone="13900000034")
    token = create_access_token(customer.id)
    # 他人会话（真实客户行以满足外键约束）
    other_customer = _create_customer(db, phone="13900000035")
    other = Conversation(customer_id=other_customer.id, status="authenticated")
    db.add(other)
    db.commit()

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.message（accept）
        ws.send_json({"type": "message", "conversation_id": other.id, "content": "越权"})
        event = ws.receive_json()

    # 不推 message.new，改推 system.message 提示无权限
    assert event["event"] == "system.message"
    # DB 无新消息
    msgs = list(db.execute(select(Message).where(Message.conversation_id == other.id)).scalars())
    assert len(msgs) == 0


def test_ws_state_transition_pushes_conversation_state(ws_client, db):
    """客户端发 state_transition → 合法转换 → 推 conversation.state 事件。

    PRD line 286 状态机：unauthenticated → authenticated 合法转换。
    """
    from app.auth.security import create_access_token
    from app.models import Conversation

    customer = _create_customer(db, phone="13900000035")
    token = create_access_token(customer.id)
    conv = Conversation(customer_id=customer.id, status="unauthenticated")
    db.add(conv)
    db.commit()

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.message（accept）
        ws.send_json(
            {"type": "state_transition", "conversation_id": conv.id, "new_state": "authenticated"}
        )
        event = ws.receive_json()

    assert event["event"] == "conversation.state"
    payload = event["data"]
    assert payload["conversation_id"] == conv.id
    assert payload["old_state"] == "unauthenticated"
    assert payload["new_state"] == "authenticated"
    assert isinstance(payload["changed_at"], str)

    # 状态持久化
    db.refresh(conv)
    assert conv.status == "authenticated"


def test_ws_state_transition_illegal_pushes_system_message(ws_client, db):
    """非法转换 → 推 system.message 错误提示，状态不变更、不推 conversation.state。"""
    from app.auth.security import create_access_token
    from app.models import Conversation

    customer = _create_customer(db, phone="13900000036")
    token = create_access_token(customer.id)
    conv = Conversation(customer_id=customer.id, status="unauthenticated")
    db.add(conv)
    db.commit()

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.message（accept）
        # 非法：unauthenticated 不可直接到 in_progress
        ws.send_json(
            {"type": "state_transition", "conversation_id": conv.id, "new_state": "in_progress"}
        )
        event = ws.receive_json()

    assert event["event"] == "system.message"
    # 状态不变
    db.refresh(conv)
    assert conv.status == "unauthenticated"
