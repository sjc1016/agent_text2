"""B9 循环7-8：坐席 WS 接入会话（take_over）+ 发消息 → message.new(source=agent)。

验收标准（issue #15）：
  坐席接入转接会话后可在 Handed-off 状态发消息，经 WS message.new 推送
  （PRD 依据：实现决策 › API 契约 / WebSocket 事件（message.new）；
              PRD 测试决策 › WS 事件 seam；用户故事 US-21）

行为：
  - take_over：坐席 WS 发送 {type: take_over, conversation_id} → 校验会话为
    handed_off 且未被接入 → 绑定 agent_id → 推坐席 system.message（接入成功）
    + 推客户 system.message（人工客服已接入）+ 审计 agent.take_over。
  - message：坐席 WS 发送 {type: message, conversation_id, content} → 校验会话
    已绑定当前坐席 → 持久化 source=agent 消息 → 推 message.new 给坐席与客户连接。
  - 未接入/已被他人接入的会话 → 坐席收 system.message 提示，不持久化、不推送。

接收说明：双连接测试（客户 + 坐席并发）用 recv_ws 替代 receive_json ——
TestClient 双 WS 连接 + 跨线程推送在 Windows/ProactorEventLoop 下偶发
portal 唤醒丢失导致 receive 永久挂起（详见 conftest.ws_recv_json）。
"""

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_agent(db, employee_id: str = "A4001"):
    from app.models import User

    agent = User(
        employee_id=employee_id,
        password_hash=_hash_password("agent-pass"),
        name="坐席四",
    )
    db.add(agent)
    db.commit()
    return agent


def _agent_token(agent) -> str:
    from app.auth.security import create_agent_access_token

    return create_agent_access_token(agent.id)


def _create_customer(db, phone: str = "13800000071"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password("x"))
    db.add(customer)
    db.commit()
    return customer


def _customer_token(customer) -> str:
    from app.auth.security import create_access_token

    return create_access_token(customer.id)


def _create_handed_off_conversation(db, customer_id: int, agent_id: int | None = None):
    from app.models import Conversation

    conv = Conversation(customer_id=customer_id, status="handed_off", agent_id=agent_id)
    db.add(conv)
    db.commit()
    return conv


def test_agent_take_over_binds_conversation_and_audits(ws_client, db, recv_ws):
    """坐席 take_over 接入 handed_off 会话 → 绑定 agent_id + 双方 system.message + 审计。"""
    from sqlalchemy import select

    from app.models import AuditLog

    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_handed_off_conversation(db, customer.id)
    customer_token = _customer_token(customer)
    agent_token = _agent_token(agent)

    with (
        ws_client.websocket_connect(f"/ws?token={customer_token}") as customer_ws,
        ws_client.websocket_connect(f"/ws?token={agent_token}") as agent_ws,
    ):
        recv_ws(customer_ws)  # 会话建立
        recv_ws(agent_ws)  # 坐席工作台已连接

        agent_ws.send_json({"type": "take_over", "conversation_id": conv.id})

        # 坐席收到接入成功提示
        agent_event = recv_ws(agent_ws)
        assert agent_event["event"] == "system.message"
        assert "接入" in agent_event["data"]["content"]
        # 客户收到人工客服接入提示
        customer_event = recv_ws(customer_ws)
        assert customer_event["event"] == "system.message"
        assert "人工客服" in customer_event["data"]["content"]

    # 会话绑定坐席
    db.refresh(conv)
    assert conv.agent_id == agent.id
    assert conv.status == "handed_off"

    # 审计：agent.take_over
    db.expire_all()
    logs = db.execute(select(AuditLog).where(AuditLog.action == "agent.take_over")).scalars().all()
    assert len(logs) == 1
    assert logs[0].actor_type == "agent"
    assert logs[0].actor_id == agent.id


def test_agent_message_after_takeover_pushes_message_new_to_both(ws_client, db, recv_ws):
    """接入后坐席发消息 → 客户与坐席连接均收到 message.new（source=agent）。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_handed_off_conversation(db, customer.id, agent_id=agent.id)
    customer_token = _customer_token(customer)
    agent_token = _agent_token(agent)

    with (
        ws_client.websocket_connect(f"/ws?token={customer_token}") as customer_ws,
        ws_client.websocket_connect(f"/ws?token={agent_token}") as agent_ws,
    ):
        recv_ws(customer_ws)
        recv_ws(agent_ws)

        agent_ws.send_json(
            {"type": "message", "conversation_id": conv.id, "content": "您好，我是人工客服小张"}
        )

        # 客户先收到 message.new（坐席消息）
        customer_event = recv_ws(customer_ws)
        assert customer_event["event"] == "message.new"
        payload = customer_event["data"]
        assert payload["conversation_id"] == conv.id
        assert payload["source"] == "agent"
        assert payload["content"] == "您好，我是人工客服小张"

        # 坐席连接也收到 message.new
        agent_event = recv_ws(agent_ws)
        assert agent_event["event"] == "message.new"
        assert agent_event["data"]["source"] == "agent"
        assert agent_event["data"]["content"] == "您好，我是人工客服小张"

    # 消息已持久化
    from sqlalchemy import select

    from app.models import Message

    db.expire_all()
    messages = (
        db.execute(
            select(Message).where(Message.conversation_id == conv.id, Message.source == "agent")
        )
        .scalars()
        .all()
    )
    assert len(messages) == 1
    assert messages[0].content == "您好，我是人工客服小张"


def test_agent_message_without_takeover_rejected(ws_client, db):
    """未接入（agent_id 为空）的会话发消息 → system.message 拒绝，消息不持久化。"""
    from sqlalchemy import select

    from app.models import Message

    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_handed_off_conversation(db, customer.id)
    agent_token = _agent_token(agent)

    with ws_client.websocket_connect(f"/ws?token={agent_token}") as agent_ws:
        agent_ws.receive_json()  # 坐席工作台已连接

        agent_ws.send_json({"type": "message", "conversation_id": conv.id, "content": "越权消息"})

        event = agent_ws.receive_json()
        assert event["event"] == "system.message"
        assert event["data"]["content"]

    db.expire_all()
    messages = db.execute(select(Message).where(Message.conversation_id == conv.id)).scalars().all()
    assert messages == []


def test_agent_take_over_already_bound_conversation_rejected(ws_client, db):
    """已被其他坐席接入的会话 → 拒绝再次接入（不覆盖 agent_id）。"""
    agent = _create_agent(db, employee_id="A4002")
    other_agent = _create_agent(db, employee_id="A4003")
    customer = _create_customer(db)
    conv = _create_handed_off_conversation(db, customer.id, agent_id=other_agent.id)
    agent_token = _agent_token(agent)

    with ws_client.websocket_connect(f"/ws?token={agent_token}") as agent_ws:
        agent_ws.receive_json()

        agent_ws.send_json({"type": "take_over", "conversation_id": conv.id})

        event = agent_ws.receive_json()
        assert event["event"] == "system.message"
        assert event["data"]["content"]

    db.refresh(conv)
    assert conv.agent_id == other_agent.id
