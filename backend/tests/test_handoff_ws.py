"""B8 循环4：WS seam — 客户触发 handoff（handoff.start + 进入队列）+ 离线兜底回呼 Ticket
+ 坐席转回推送 handoff.end（会话恢复）。

验收标准（issue #17）：
  - 6 类条件触发 Handoff，推送 handoff.start，会话进入 Handed-off，助理退至后台（US-15/16）
  - 全忙超阈值或非服务时间创建回呼请求 Ticket 派单到 Skill Group，助理不强制结束会话（US-29）
  - 坐席接手后转回助理推送 handoff.end，会话恢复（US-26）

行为：
  - 客户 WS 发送 {type: handoff, conversation_id, reason} → trigger_handoff 执行 →
    推 system.message（转接提示）+ conversation.state（→ handed_off）+ handoff.start
    （reason / offline_fallback / ticket_id）。
  - 无在线坐席（全忙超阈值）→ 离线兜底：handoff.start.offline_fallback=True 且
    ticket_id 指向已派单的回呼请求 Ticket（工单类，dispatched，skill_group 标注）。
  - 坐席 transfer_back → 客户收 handoff.end，会话恢复 authenticated。
  - 非法 reason / 他人会话 / 已在转接中 → system.message 拒绝，状态不变更。

双连接接收统一用 recv_ws（规避 Windows 下 TestClient portal 唤醒丢失，见 conftest）。
"""

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_agent(db, employee_id: str = "A7001", status: str = "online"):
    from app.models import User

    agent = User(
        employee_id=employee_id,
        password_hash=_hash_password("agent-pass"),
        name="坐席七",
        status=status,
    )
    db.add(agent)
    db.commit()
    return agent


def _agent_token(agent) -> str:
    from app.auth.security import create_agent_access_token

    return create_agent_access_token(agent.id)


def _create_customer(db, phone: str = "13800000131"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password("x"))
    db.add(customer)
    db.commit()
    return customer


def _customer_token(customer) -> str:
    from app.auth.security import create_access_token

    return create_access_token(customer.id)


def _create_conversation(
    db, customer_id: int, status: str = "authenticated", agent_id: int | None = None
):
    from app.models import Conversation

    conv = Conversation(customer_id=customer_id, status=status, agent_id=agent_id)
    db.add(conv)
    db.commit()
    return conv


def test_client_handoff_pushes_start_and_enters_queue(ws_client, db):
    """在线坐席 + 服务时间内 → 正常转接：handoff.start + conversation.state + 进入队列。"""
    from app.models import Ticket

    _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    token = _customer_token(customer)

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # 会话建立 system.message
        ws.send_json({"type": "handoff", "conversation_id": conv.id, "reason": "explicit_request"})

        # 转接提示
        hint = ws.receive_json()
        assert hint["event"] == "system.message"
        # 会话状态 → handed_off
        state = ws.receive_json()
        assert state["event"] == "conversation.state"
        assert state["data"]["old_state"] == "authenticated"
        assert state["data"]["new_state"] == "handed_off"
        # handoff.start
        start = ws.receive_json()
        assert start["event"] == "handoff.start"
        payload = start["data"]
        assert payload["conversation_id"] == conv.id
        assert payload["reason"] == "explicit_request"
        assert payload["offline_fallback"] is False
        assert payload["ticket_id"] is None
        assert isinstance(payload["changed_at"], str)

    # 会话进入待接入队列（handed_off + agent_id 为空 = 待接入，US-20）
    db.refresh(conv)
    assert conv.status == "handed_off"
    assert conv.agent_id is None
    # 正常转接不创建回呼 Ticket
    assert list(db.query(Ticket).all()) == []

    # 待接入队列可见该会话（/agents/queues 数据来源 seam）
    from app.agents.service import list_pending_queue_entries

    entries = list_pending_queue_entries(db)
    assert any(e.conversation.id == conv.id for e in entries)


def test_handoff_offline_fallback_creates_callback_ticket(ws_client, db):
    """无在线坐席（全忙超阈值）→ 离线兜底：回呼请求 Ticket 创建并派单 + 不强制结束会话。"""
    from app.models import Ticket

    _create_agent(db, status="offline")  # 全忙：无在线坐席
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    token = _customer_token(customer)

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json(
            {"type": "handoff", "conversation_id": conv.id, "reason": "negative_sentiment"}
        )

        ws.receive_json()  # system.message 转接提示
        state = ws.receive_json()
        assert state["event"] == "conversation.state"
        start = ws.receive_json()
        assert start["event"] == "handoff.start"
        payload = start["data"]
        assert payload["reason"] == "negative_sentiment"
        assert payload["offline_fallback"] is True
        assert payload["ticket_id"] is not None

    # 回呼请求 Ticket：工单类 + 派单到默认技能组 + 内容含回呼标记
    ticket = db.get(Ticket, payload["ticket_id"])
    assert ticket is not None
    assert ticket.ticket_type.value == "ticketing"
    assert ticket.status.value == "dispatched"
    assert ticket.skill_group == "套餐业务组"
    assert "回呼请求" in ticket.content
    # 不强制结束会话：进入待接入队列（非 closed）
    db.refresh(conv)
    assert conv.status == "handed_off"


def test_handoff_custom_skill_group(ws_client, db):
    """离线兜底可指定 Skill Group（按用户意图路由到对应组）。"""
    _create_agent(db, status="break")
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    token = _customer_token(customer)

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json(
            {
                "type": "handoff",
                "conversation_id": conv.id,
                "reason": "compliance_risk",
                "skill_group": "投诉处理组",
            }
        )
        ws.receive_json()  # system.message
        ws.receive_json()  # conversation.state
        start = ws.receive_json()

    assert start["event"] == "handoff.start"
    assert start["data"]["offline_fallback"] is True

    from app.models import Ticket

    ticket = db.get(Ticket, start["data"]["ticket_id"])
    assert ticket.skill_group == "投诉处理组"


def test_handoff_invalid_reason_rejected(ws_client, db):
    """非法 reason → system.message 拒绝，会话状态不变更。"""
    _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    token = _customer_token(customer)

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"type": "handoff", "conversation_id": conv.id, "reason": "bad_reason"})

        event = ws.receive_json()
        assert event["event"] == "system.message"
        assert event["data"]["content"]

    db.refresh(conv)
    assert conv.status == "authenticated"


def test_handoff_other_customer_conversation_rejected(ws_client, db):
    """他人会话 → system.message 拒绝，不泄露存在性。"""
    _create_agent(db)
    customer = _create_customer(db)
    other_customer = _create_customer(db, phone="13800000132")
    conv = _create_conversation(db, other_customer.id)
    token = _customer_token(customer)

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"type": "handoff", "conversation_id": conv.id, "reason": "explicit_request"})

        event = ws.receive_json()
        assert event["event"] == "system.message"
        assert event["data"]["content"]

    db.refresh(conv)
    assert conv.status == "authenticated"


def test_handoff_already_handed_off_rejected(ws_client, db):
    """已在转接中 → system.message 拒绝（不重复触发/不重复建回呼 Ticket）。"""
    _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id, status="handed_off")
    token = _customer_token(customer)

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"type": "handoff", "conversation_id": conv.id, "reason": "explicit_request"})

        event = ws.receive_json()
        assert event["event"] == "system.message"
        assert event["data"]["content"]

    db.refresh(conv)
    assert conv.status == "handed_off"


def test_handoff_end_pushed_on_transfer_back(ws_client, db, recv_ws):
    """坐席转回助理 → 客户收 handoff.end，会话恢复 authenticated（US-26）。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id, status="handed_off", agent_id=agent.id)
    customer_token = _customer_token(customer)
    agent_token = _agent_token(agent)

    with (
        ws_client.websocket_connect(f"/ws?token={customer_token}") as customer_ws,
        ws_client.websocket_connect(f"/ws?token={agent_token}") as agent_ws,
    ):
        recv_ws(customer_ws)  # 会话建立
        recv_ws(agent_ws)  # 坐席工作台已连接

        agent_ws.send_json({"type": "state_transition", "conversation_id": conv.id})

        # 坐席：system.message 确认 → conversation.state → handoff.end
        agent_hint = recv_ws(agent_ws)
        assert agent_hint["event"] == "system.message"
        agent_state = recv_ws(agent_ws)
        assert agent_state["event"] == "conversation.state"
        agent_end = recv_ws(agent_ws)
        assert agent_end["event"] == "handoff.end"
        assert agent_end["data"]["conversation_id"] == conv.id

        # 客户：conversation.state → system.message 提示 → handoff.end
        customer_state = recv_ws(customer_ws)
        assert customer_state["event"] == "conversation.state"
        assert customer_state["data"]["new_state"] == "authenticated"
        customer_hint = recv_ws(customer_ws)
        assert customer_hint["event"] == "system.message"
        customer_end = recv_ws(customer_ws)
        assert customer_end["event"] == "handoff.end"
        assert customer_end["data"]["conversation_id"] == conv.id

    # 会话恢复 + 坐席解除绑定
    db.refresh(conv)
    assert conv.status == "authenticated"
    assert conv.agent_id is None
