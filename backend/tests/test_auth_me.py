"""B1 循环4：JWT Authorization header 鉴权（/auth/me）。

验收标准（issue #4）：
  REST Authorization header 鉴权生效
  （PRD 依据：实现决策 › 认证与会话；测试决策 › HTTP 集成 seam）

/auth/me 为受保护端点：无 token / 无效 token → 401；有效 access token → 返回当前客户。
"""

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


async def test_me_without_token_returns_401(db_client):
    response = await db_client.get("/auth/me")
    assert response.status_code == 401


async def test_me_with_invalid_token_returns_401(db_client):
    response = await db_client.get(
        "/auth/me",
        headers={"Authorization": "Bearer not.a.valid.token"},
    )
    assert response.status_code == 401


async def test_me_with_valid_token_returns_customer(db_client, db):
    from app.models import Customer

    customer = Customer(
        phone="13900000003",
        service_password_hash=_hash_password("svc12345"),
    )
    db.add(customer)
    db.commit()

    login_resp = await db_client.post(
        "/auth/login",
        json={"phone": "13900000003", "service_password": "svc12345"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    response = await db_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["phone"] == "13900000003"
    assert data["id"] == customer.id
