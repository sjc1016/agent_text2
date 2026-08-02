"""B1 循环2-3：POST /auth/login 认证成功/失败 + 审计日志。

验收标准（issue #4）：
  - 循环2：有效手机号+服务密码返回 access/refresh token（US-2）
  - 循环3：错误服务密码返回 401，审计日志记录失败（CONTEXT.md › 审计日志）
  （PRD 依据：实现决策 › 认证与会话；测试决策 › HTTP 集成 seam）
"""

import bcrypt
import pytest
from sqlalchemy import select

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    """测试用 hash helper（直接用 bcrypt，不耦合 app.auth 实现）。"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


async def test_login_valid_credentials_returns_tokens(db_client, db):
    from app.models import Customer

    customer = Customer(
        phone="13800000001",
        service_password_hash=_hash_password("svc12345"),
    )
    db.add(customer)
    db.commit()

    response = await db_client.post(
        "/auth/login",
        json={"phone": "13800000001", "service_password": "svc12345"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str) and data["access_token"]
    assert isinstance(data["refresh_token"], str) and data["refresh_token"]


async def test_login_wrong_password_returns_401_and_audit_log(db_client, db):
    from app.models import AuditLog, Customer

    customer = Customer(
        phone="13800000002",
        service_password_hash=_hash_password("correct-pwd"),
    )
    db.add(customer)
    db.commit()

    response = await db_client.post(
        "/auth/login",
        json={"phone": "13800000002", "service_password": "wrong-pwd"},
    )

    assert response.status_code == 401
    # 审计日志记录认证失败（CONTEXT.md › 审计日志：服务密码认证失败）
    db.expire_all()
    logs = (
        db.execute(select(AuditLog).where(AuditLog.action == "auth.login.failure")).scalars().all()
    )
    assert len(logs) == 1
    assert logs[0].actor_type == "customer"
