"""B12 循环5（issue #44 AC5）：客户在 handed_off 会话发消息 → 双端推送（US-22）。

验收标准（issue #44 AC5）：
  客户在 handed_off 会话发消息时：user 消息持久化、客户连接收到 message.new、
  接入坐席（conv.agent_id）经 hub.push_to_agent 实时收到 message.new；不进入 LLM
  （PRD 依据：实现决策 › WebSocket 事件（message.new）；
              测试决策 › WS 事件 seam；用户故事 US-22（对话））

行为：
  - 已接入坐席（agent_id 非空）的 handed_off 会话：客户发消息 → user 消息持久化，
    客户连接与坐席连接均收到 message.new（source=user）；不产生 llm.token 与
    assistant 回复（不进入 LLM 对话流）。
  - 未接入坐席（agent_id 为空）的 handed_off 会话：客户连接收到 message.new，
    无坐席推送目标（静默跳过）。

接收说明：双连接测试用 recv_ws 替代 receive_json（Windows/ProactorEventLoop 下
TestClient 双 WS 并发推送的 portal 唤醒问题，见 conftest.ws_recv_json）。
"""

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_agent(db, employee_id: str = "A5005"):
    from app.models import User

    agent = User(
        employee_id=employee_id,
        password_hash=_hash_password("agent-pass"),
        name="坐席五",
    )
    db.add(agent)
    db.commit()
    return agent


def _agent_token(agent) -> str:
    from app.auth.security import create_agent_access_token

    return create_agent_access_token(agent.id)


def _create_customer(db, phone: str = "13800000095"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password("x"))
    db.add(customer)
    db.commit()
    return customer


def _customer_token(customer) -> str:
    from app.auth.security import create_access_token

    return create_access_token(customer.id)


def _create_handed_off_conversation(db, customer_id: int, agent_id: int | None):
    from app.models import Conversation

    conv = Conversation(customer_id=customer_id, status="handed_off", agent_id=agent_id)
    db.add(conv)
    db.commit()
    return conv


def test_client_message_in_handed_off_pushes_to_agent(ws_client, db, recv_ws):
    """已接入坐席的 handed_off 会话：客户消息持久化 + 客户/坐席双端 message.new。"""
    from sqlalchemy import select

    from app.models import Message

    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_handed_off_conversation(db, customer.id, agent_id=agent.id)
    customer_token = _customer_token(customer)
    agent_token = _agent_token(agent)

    with (
        ws_client.websocket_connect(f"/ws?token={customer_token}") as customer_ws,
        ws_client.websocket_connect(f"/ws?token={agent_token}") as agent_ws,
    ):
        recv_ws(customer_ws)  # 会话已建立
        recv_ws(agent_ws)  # 坐席工作台已连接

        customer_ws.send_json(
            {"type": "message", "conversation_id": conv.id, "content": "还在吗？"}
        )

        # 客户连接先收到 message.new（即时回显，source=user）
        customer_event = recv_ws(customer_ws)
        assert customer_event["event"] == "message.new"
        assert customer_event["data"]["source"] == "user"
        assert customer_event["data"]["content"] == "还在吗？"
        assert customer_event["data"]["conversation_id"] == conv.id

        # 接入坐席经 hub.push_to_agent 收到 message.new
        agent_event = recv_ws(agent_ws)
        assert agent_event["event"] == "message.new"
        assert agent_event["data"]["source"] == "user"
        assert agent_event["data"]["content"] == "还在吗？"

    # user 消息已持久化
    db.expire_all()
    messages = db.execute(select(Message).where(Message.conversation_id == conv.id)).scalars().all()
    assert len(messages) == 1
    assert messages[0].source.value == "user"
    assert messages[0].content == "还在吗？"


def test_client_message_in_handed_off_skips_llm(ws_client, db, recv_ws):
    """handed_off 会话客户消息不进入 LLM：无 llm.token / 无 assistant 回复。"""
    from sqlalchemy import select

    from app.models import Message

    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_handed_off_conversation(db, customer.id, agent_id=agent.id)
    customer_token = _customer_token(customer)

    with ws_client.websocket_connect(f"/ws?token={customer_token}") as customer_ws:
        recv_ws(customer_ws)  # 会话已建立

        customer_ws.send_json({"type": "message", "conversation_id": conv.id, "content": "你好"})

        # 仅收到 message.new（无 llm.token / assistant 回复）
        event = recv_ws(customer_ws)
        assert event["event"] == "message.new"
        assert event["data"]["source"] == "user"

    db.expire_all()
    messages = db.execute(select(Message).where(Message.conversation_id == conv.id)).scalars().all()
    assert [m.source.value for m in messages] == ["user"]  # 仅 user 消息，无 assistant


def test_client_message_in_handed_off_without_agent(ws_client, db, recv_ws):
    """未接入坐席（agent_id 为空）的 handed_off 会话：客户收到 message.new，推送静默跳过。"""
    customer = _create_customer(db)
    conv = _create_handed_off_conversation(db, customer.id, agent_id=None)
    customer_token = _customer_token(customer)

    with ws_client.websocket_connect(f"/ws?token={customer_token}") as customer_ws:
        recv_ws(customer_ws)  # 会话已建立

        customer_ws.send_json({"type": "message", "conversation_id": conv.id, "content": "在吗"})

        event = recv_ws(customer_ws)
        assert event["event"] == "message.new"
        assert event["data"]["source"] == "user"
