"""#65：/auth/refresh 端点（access 过期后用 refresh token 换新 access token）。

验收标准（issue #65）：
  - 有效 refresh token（7d，type=refresh）→ 200 + 新 access_token
  - refresh token 无效/过期/类型不符/主体不存在 → 401（前端据此 logout 回访客态）

PRD 依据：ADR 0004（access 2h / refresh 7d 无状态 JWT）；
CONTEXT › 认证语义「无凭据 → 401」。refresh 端点本身不校验服务密码
（凭 refresh token 单因素换发，前端仅在已持有效会话时使用）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.auth.security import create_access_token, create_refresh_token

pytestmark = pytest.mark.integration


def _secret() -> str:
    from app.config import get_settings

    return get_settings().jwt_secret


def _expired_refresh_token(customer_id: int) -> str:
    """构造已过期的 refresh token（exp 在过去）。"""
    payload = {
        "sub": str(customer_id),
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        "type": "refresh",
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def _create_customer(db, phone: str = "13900000070", password: str = "svc12345"):
    import bcrypt

    from app.models import Customer

    customer = Customer(
        phone=phone,
        service_password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode(),
    )
    db.add(customer)
    db.commit()
    return customer


async def test_refresh_with_valid_token_returns_new_access_token(db_client, db):
    """有效 refresh token → 200 + access_token（type=access，可访问受保护端点）。"""
    customer = _create_customer(db)
    refresh_token = create_refresh_token(customer.id)

    response = await await_refresh(db_client, refresh_token)

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]

    # 新 access token 可访问受保护端点（/auth/me）
    me = await db_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {data['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["id"] == customer.id


async def test_refresh_with_expired_token_returns_401(db_client, db):
    """过期 refresh token → 401（前端据此清除凭证回访客态）。"""
    customer = _create_customer(db)

    response = await await_refresh(db_client, _expired_refresh_token(customer.id))

    assert response.status_code == 401


async def test_refresh_with_access_token_returns_401(db_client, db):
    """access token 冒充 refresh token → 401（type=refresh 严格校验，拒绝越权换发）。"""
    customer = _create_customer(db)

    response = await await_refresh(db_client, create_access_token(customer.id))

    assert response.status_code == 401


async def test_refresh_with_nonexistent_customer_returns_401(db_client):
    """refresh token 的 sub 对应用户不存在 → 401（主体存在性校验）。"""
    response = await await_refresh(db_client, create_refresh_token(999999))

    assert response.status_code == 401


async def test_refresh_with_garbage_token_returns_401(db_client):
    """非法 token 字符串 → 401（jwt 解码失败收敛为统一 401 文案）。"""
    response = await await_refresh(db_client, "not-a-jwt")

    assert response.status_code == 401


async def test_refresh_without_token_returns_422(db_client):
    """缺失 refresh_token 字段 → 422（Pydantic 请求体验证）。"""
    response = await db_client.post("/auth/refresh", json={})
    assert response.status_code == 422


async def await_refresh(client, refresh_token: str):
    return await client.post("/auth/refresh", json={"refresh_token": refresh_token})
