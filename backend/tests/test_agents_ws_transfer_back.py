"""B9 循环9：坐席 WS 转回助理（US-26）。

验收标准（issue #15）：
  坐席转回助理将会话状态从 Handed-off 恢复
  （PRD 依据：实现决策 › API 契约 / WebSocket 事件（conversation.state）；
              PRD 测试决策 › WS 事件 seam；用户故事 US-26）

行为：
  - transfer_back：坐席 WS 发送 {type: state_transition, conversation_id} → 校验
    会话已接入当前坐席且状态为 handed_off → 状态流转 handed_off → authenticated
    + agent_id 置空（恢复助理接管）→ 坐席收 system.message 确认 + conversation.state；
    客户收 conversation.state + system.message（已转回助理）+ 审计 agent.transfer_back。
  - 非法（未接入 / 非 handed_off）→ 坐席收 system.message 提示，状态不变更。

双连接接收统一用 recv_ws（规避 Windows 下 TestClient portal 唤醒丢失，见 conftest）。
"""

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_agent(db, employee_id: str = "A5001"):
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


def _create_customer(db, phone: str = "13800000091"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password("x"))
    db.add(customer)
    db.commit()
    return customer


def _customer_token(customer) -> str:
    from app.auth.security import create_access_token

    return create_access_token(customer.id)


def _create_conversation(
    db, customer_id: int, status: str = "handed_off", agent_id: int | None = None
):
    from app.models import Conversation

    conv = Conversation(customer_id=customer_id, status=status, agent_id=agent_id)
    db.add(conv)
    db.commit()
    return conv


def test_agent_transfer_back_restores_conversation_and_audits(ws_client, db, recv_ws):
    """转回助理 → handed_off→authenticated + agent_id 置空 + 双方事件 + 审计。"""
    from sqlalchemy import select

    from app.models import AuditLog

    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id, agent_id=agent.id)
    customer_token = _customer_token(customer)
    agent_token = _agent_token(agent)

    with (
        ws_client.websocket_connect(f"/ws?token={customer_token}") as customer_ws,
        ws_client.websocket_connect(f"/ws?token={agent_token}") as agent_ws,
    ):
        recv_ws(customer_ws)  # 会话建立
        recv_ws(agent_ws)  # 坐席工作台已连接

        agent_ws.send_json({"type": "state_transition", "conversation_id": conv.id})

        # server 顺序：坐席 system.message 确认 → 坐席 conversation.state
        agent_event = recv_ws(agent_ws)
        assert agent_event["event"] == "system.message"
        assert "已转回" in agent_event["data"]["content"]
        agent_state = recv_ws(agent_ws)
        assert agent_state["event"] == "conversation.state"
        assert agent_state["data"]["old_state"] == "handed_off"
        assert agent_state["data"]["new_state"] == "authenticated"

        # 客户：conversation.state → system.message（已转回助理）
        customer_state = recv_ws(customer_ws)
        assert customer_state["event"] == "conversation.state"
        assert customer_state["data"]["conversation_id"] == conv.id
        assert customer_state["data"]["new_state"] == "authenticated"
        customer_hint = recv_ws(customer_ws)
        assert customer_hint["event"] == "system.message"
        assert "已转回" in customer_hint["data"]["content"]

    # 状态恢复 + 坐席解除绑定（agent_id 置空 → 回到待接入语义的恢复态）
    db.refresh(conv)
    assert conv.status == "authenticated"
    assert conv.agent_id is None

    # 审计：agent.transfer_back
    db.expire_all()
    logs = (
        db.execute(select(AuditLog).where(AuditLog.action == "agent.transfer_back")).scalars().all()
    )
    assert len(logs) == 1
    assert logs[0].actor_type == "agent"
    assert logs[0].actor_id == agent.id


def test_agent_transfer_back_without_takeover_rejected(ws_client, db, recv_ws):
    """未接入（agent_id 为空）的会话 → 拒绝转回，状态不变更。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    agent_token = _agent_token(agent)

    with ws_client.websocket_connect(f"/ws?token={agent_token}") as agent_ws:
        recv_ws(agent_ws)  # 坐席工作台已连接

        agent_ws.send_json({"type": "state_transition", "conversation_id": conv.id})

        event = recv_ws(agent_ws)
        assert event["event"] == "system.message"
        assert event["data"]["content"]

    db.refresh(conv)
    assert conv.status == "handed_off"
    assert conv.agent_id is None


def test_agent_transfer_back_non_handed_off_rejected(ws_client, db, recv_ws):
    """非 handed_off 状态（authenticated）→ 拒绝转回，状态不变更。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id, status="authenticated", agent_id=agent.id)
    agent_token = _agent_token(agent)

    with ws_client.websocket_connect(f"/ws?token={agent_token}") as agent_ws:
        recv_ws(agent_ws)

        agent_ws.send_json({"type": "state_transition", "conversation_id": conv.id})

        event = recv_ws(agent_ws)
        assert event["event"] == "system.message"
        assert event["data"]["content"]

    db.refresh(conv)
    assert conv.status == "authenticated"
