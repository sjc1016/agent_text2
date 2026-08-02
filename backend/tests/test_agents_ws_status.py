"""B9 循环5：坐席 WS 连接 + agent.status 推送（US-30）。

验收标准（issue #15）：
  PUT /agents/status 切换在线/离线/小休，经 WS `agent.status` 推送
  （PRD 依据：PRD 实现决策 › API 契约 /agents/status；
              PRD 测试决策 › WS 事件 seam；用户故事 US-30）

WS 鉴权：坐席用 agent_access JWT 经查询参数连接 /ws；握手失败 close 4401。
状态切换经 hub 向该坐席活跃连接推送 agent.status（REST 与 WS 独立连接，
推送方不在 WS 上下文内 —— 复用 B7 ConnectionHub 跨请求推送模式）。
"""

import bcrypt
import pytest
from starlette.websockets import WebSocketDisconnect

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_agent(db, employee_id: str = "A3001"):
    from app.models import User

    agent = User(employee_id=employee_id, password_hash=_hash_password("agent-pass"), name="坐席三")
    db.add(agent)
    db.commit()
    return agent


def _agent_token(agent) -> str:
    from app.auth.security import create_agent_access_token

    return create_agent_access_token(agent.id)


def test_ws_agent_connection_accepted_with_agent_token(ws_client, db):
    """坐席 agent_access token 连接 /ws → accept + 推 system.message（坐席工作台已连接）。"""
    agent = _create_agent(db)
    token = _agent_token(agent)

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        event = ws.receive_json()

    assert event["event"] == "system.message"
    assert isinstance(event["data"]["content"], str) and event["data"]["content"]


def test_ws_with_nonexistent_agent_token_rejected(ws_client, db):
    """token sub 指向不存在的坐席 → close 4401。"""
    from app.auth.security import create_agent_access_token

    token = create_agent_access_token(999999)
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        ws_client.websocket_connect(f"/ws?token={token}"),
    ):
        pass
    assert exc.value.code == 4401


def test_ws_customer_token_cannot_receive_agent_events(ws_client, db):
    """客户 access token 连接后，坐席状态切换不会推送给客户连接（主体隔离）。"""
    from app.auth.security import create_access_token
    from app.models import Customer

    customer = Customer(phone="13900000041", service_password_hash=_hash_password("x"))
    db.add(customer)
    db.commit()
    customer_token = create_access_token(customer.id)

    with ws_client.websocket_connect(f"/ws?token={customer_token}") as ws:
        event = ws.receive_json()
        assert event["event"] == "system.message"


def test_agent_status_change_pushes_agent_status_event(ws_client, db):
    """坐席经 REST 切换状态 → 该坐席活跃 WS 连接收到 agent.status 事件。"""
    agent = _create_agent(db)
    token = _agent_token(agent)

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.message（accept）
        response = ws_client.put(
            "/agents/status",
            json={"status": "online"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        event = ws.receive_json()
        assert event["event"] == "agent.status"
        payload = event["data"]
        assert payload["agent_id"] == agent.id
        assert payload["status"] == "online"
        assert isinstance(payload["changed_at"], str)

        # DB 持久化
        db.refresh(agent)
        assert agent.status == "online"


def test_agent_status_change_pushes_to_break_and_offline(ws_client, db):
    """小休/离线状态同样推送 agent.status。"""
    agent = _create_agent(db, employee_id="A3002")
    token = _agent_token(agent)

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.message
        for status in ("break", "offline"):
            response = ws_client.put(
                "/agents/status",
                json={"status": status},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200
            event = ws.receive_json()
            assert event["event"] == "agent.status"
            assert event["data"]["status"] == status
