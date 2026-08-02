"""B9 循环1-2：POST /agents/login 坐席登录（US-19）。

验收标准（issue #15）：
  POST /agents/login 工号+密码登录成功返回坐席 JWT，失败返回 401
  （PRD 依据：PRD 实现决策 › API 契约 /agents/login；
              PRD 测试决策 › HTTP 集成 seam；用户故事 US-19）

坐席账号（User 模型）由 B1 建表，本切片实现登录：工号（employee_id）+ 密码
认证成功 → 颁发坐席 JWT（type=agent_access，与客户 access 区分主体）。
"""

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    """测试用 hash helper（直接用 bcrypt，不耦合 app.auth 实现）。"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_agent(db, employee_id: str = "A1001", password: str = "agent-pass"):
    from app.models import User

    agent = User(
        employee_id=employee_id,
        password_hash=_hash_password(password),
        name="坐席一",
    )
    db.add(agent)
    db.commit()
    return agent


async def test_agent_login_valid_credentials_returns_tokens(db_client, db):
    """工号+密码正确 → 200 + 坐席 access/refresh token。"""
    _create_agent(db)

    response = await db_client.post(
        "/agents/login",
        json={"employee_id": "A1001", "password": "agent-pass"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str) and data["access_token"]
    assert isinstance(data["refresh_token"], str) and data["refresh_token"]


async def test_agent_login_token_is_agent_access_type(db_client, db):
    """坐席 JWT 的 token type 为 agent_access（与客户 access 区分主体）。"""
    from app.auth.security import decode_token

    _create_agent(db)

    response = await db_client.post(
        "/agents/login",
        json={"employee_id": "A1001", "password": "agent-pass"},
    )

    payload = decode_token(response.json()["access_token"])
    assert payload["type"] == "agent_access"


async def test_agent_login_wrong_password_returns_401_and_audit(db_client, db):
    """密码错误 → 401 + 审计日志记录失败（CONTEXT › 审计日志 › 坐席登录）。"""
    from sqlalchemy import select

    from app.models import AuditLog

    _create_agent(db)

    response = await db_client.post(
        "/agents/login",
        json={"employee_id": "A1001", "password": "wrong-pass"},
    )

    assert response.status_code == 401
    db.expire_all()
    logs = (
        db.execute(select(AuditLog).where(AuditLog.action == "agent.login.failure")).scalars().all()
    )
    assert len(logs) == 1
    assert logs[0].actor_type == "agent"
    assert logs[0].detail == {"employee_id": "A1001"}


async def test_agent_login_unknown_employee_returns_401(db_client, db):
    """工号不存在 → 401（不泄露账号存在性）。"""
    response = await db_client.post(
        "/agents/login",
        json={"employee_id": "NO-SUCH", "password": "whatever"},
    )

    assert response.status_code == 401


async def test_agent_login_success_writes_audit(db_client, db):
    """登录成功写入审计日志（actor_type=agent，坐席操作留痕）。"""
    from sqlalchemy import select

    from app.models import AuditLog

    agent = _create_agent(db)

    response = await db_client.post(
        "/agents/login",
        json={"employee_id": "A1001", "password": "agent-pass"},
    )
    assert response.status_code == 200

    db.expire_all()
    logs = (
        db.execute(select(AuditLog).where(AuditLog.action == "agent.login.success")).scalars().all()
    )
    assert len(logs) == 1
    assert logs[0].actor_type == "agent"
    assert logs[0].actor_id == agent.id
