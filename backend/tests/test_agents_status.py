"""B9 循环3-4：PUT /agents/status 坐席状态切换（US-30）。

验收标准（issue #15）：
  PUT /agents/status 切换在线/离线/小休，经 WS `agent.status` 推送
  （PRD 依据：PRD 实现决策 › API 契约 /agents/status；
              PRD 测试决策 › HTTP 集成 seam + WS 事件 seam；用户故事 US-30）

本文件覆盖 HTTP seam（鉴权 + 状态持久化 + 非法状态 422）；
WS agent.status 推送（hub）在 test_agents_ws_status.py 覆盖。
"""

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_agent(db, employee_id: str = "A2001"):
    from app.models import User

    agent = User(employee_id=employee_id, password_hash=_hash_password("agent-pass"), name="坐席二")
    db.add(agent)
    db.commit()
    return agent


def _agent_token(agent) -> str:
    from app.auth.security import create_agent_access_token

    return create_agent_access_token(agent.id)


async def test_agent_status_update_persists(db_client, db):
    """坐席切换状态 → 200 + 响应含新状态 + DB 持久化。"""
    agent = _create_agent(db)
    token = _agent_token(agent)

    response = await db_client.put(
        "/agents/status",
        json={"status": "break"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == agent.id
    assert data["employee_id"] == "A2001"
    assert data["status"] == "break"
    db.refresh(agent)
    assert agent.status == "break"


async def test_agent_status_switch_through_all_states(db_client, db):
    """三态（在线/小休/离线）均可切换（US-30）。"""
    agent = _create_agent(db, employee_id="A2002")
    token = _agent_token(agent)

    for status in ("online", "break", "offline"):
        response = await db_client.put(
            "/agents/status",
            json={"status": status},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == status
        db.refresh(agent)
        assert agent.status == status


async def test_agent_status_invalid_value_returns_422(db_client, db):
    """非法状态（非三态）→ 422（schema Literal 校验）。"""
    agent = _create_agent(db)
    token = _agent_token(agent)

    response = await db_client.put(
        "/agents/status",
        json={"status": "busy"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


async def test_agent_status_without_token_returns_401(db_client, db):
    """未携带坐席 JWT → 401。"""
    response = await db_client.put("/agents/status", json={"status": "online"})

    assert response.status_code == 401


async def test_agent_status_with_customer_token_rejected(db_client, db):
    """客户 access token 访问坐席端点 → 401（主体隔离）。"""
    from app.auth.security import create_access_token
    from app.models import Customer

    _create_agent(db)
    customer = Customer(phone="13900000001", service_password_hash=_hash_password("x"))
    db.add(customer)
    db.commit()

    response = await db_client.put(
        "/agents/status",
        json={"status": "online"},
        headers={"Authorization": f"Bearer {create_access_token(customer.id)}"},
    )

    assert response.status_code == 401
