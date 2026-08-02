"""B1 循环5：办理执行复核 /auth/reauth。

验收标准（issue #4）：
  POST /auth/reauth 服务密码复核通过返回可执行凭证，失败返回 401
  （PRD 依据：实现决策 › 认证与会话 / 办理执行复核；
   测试决策 › HTTP 集成 seam；用户故事 US-12）

CONTEXT › 办理执行复核 (Transaction Re-auth)：办理类 Ticket 从「待执行」进入
「执行中」前，必须再次输入 Service Password 验证 —— 单因素认证的补偿控制。
本端点受 access token 保护，复核通过颁发短期 execute_token（type=execute）。
"""

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


async def _login(db_client, phone: str, password: str) -> str:
    resp = await db_client.post(
        "/auth/login",
        json={"phone": phone, "service_password": password},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


async def test_reauth_with_valid_password_returns_execute_token(db_client, db):
    """有效 access token + 正确服务密码 → 200 + execute_token（办理执行凭证）。"""
    from app.models import Customer

    customer = Customer(
        phone="13900000004",
        service_password_hash=_hash_password("svc12345"),
    )
    db.add(customer)
    db.commit()

    token = await _login(db_client, "13900000004", "svc12345")
    response = await db_client.post(
        "/auth/reauth",
        json={"service_password": "svc12345"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["execute_token"]


async def test_reauth_with_wrong_password_returns_401_and_audit(db_client, db):
    """错误服务密码 → 401；审计日志记录 auth.reauth.failure（合规留痕）。"""
    from app.models import AuditLog, Customer

    customer = Customer(
        phone="13900000005",
        service_password_hash=_hash_password("svc12345"),
    )
    db.add(customer)
    db.commit()

    token = await _login(db_client, "13900000005", "svc12345")
    response = await db_client.post(
        "/auth/reauth",
        json={"service_password": "wrong-password"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    # 审计留痕：CONTEXT › 审计日志 要求服务密码认证（成功/失败）必须记录
    failure_logs = (
        db.query(AuditLog)
        .filter(
            AuditLog.actor_id == customer.id,
            AuditLog.action == "auth.reauth.failure",
        )
        .all()
    )
    assert len(failure_logs) == 1


async def test_reauth_without_access_token_returns_401(db_client):
    """无 access token → 401（reauth 是受保护端点）。"""
    response = await db_client.post(
        "/auth/reauth",
        json={"service_password": "svc12345"},
    )
    assert response.status_code == 401


async def test_reauth_success_writes_audit_log(db_client, db):
    """复核成功 → 审计日志记录 auth.reauth.success（合规留痕）。"""
    from app.models import AuditLog, Customer

    customer = Customer(
        phone="13900000006",
        service_password_hash=_hash_password("svc12345"),
    )
    db.add(customer)
    db.commit()

    token = await _login(db_client, "13900000006", "svc12345")
    response = await db_client.post(
        "/auth/reauth",
        json={"service_password": "svc12345"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200

    success_logs = (
        db.query(AuditLog)
        .filter(
            AuditLog.actor_id == customer.id,
            AuditLog.action == "auth.reauth.success",
        )
        .all()
    )
    assert len(success_logs) == 1
