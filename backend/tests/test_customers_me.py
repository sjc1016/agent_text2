"""B13 循环1（issue #53 AC1）：客户读取自身账户资料（US-17）。

验收标准（issue #53 AC1）：
  客户认证可读取自身账户资料（GET /customers/me：
  话费余额/套餐名/合约到期；未认证 → 401；复用 B12 坐席侧同一数据源）
  （PRD 依据：实现决策 › API 契约（RESTful 端点 /customers/me）；
              用户故事 US-17（查看会话历史与账号信息））

行为：
  - 客户认证 → 200 + 客户资料（号码/名称）+ 账户信息（余额/套餐名/合约到期，
    复用 B12 /agents/customers/{id} 同一数据源 CustomerAccount）。
  - Customer 存在但无账户记录 → 404（不编造账户信息，与坐席侧一致）。
  - 无 token / 坐席 token → 401（主体隔离）。
"""

from datetime import date

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_customer(db, phone: str = "13800000101"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password("x"), name="张三")
    db.add(customer)
    db.commit()
    return customer


def _create_account(db, customer_id: int) -> None:
    from app.models.inquiry import CustomerAccount

    db.add(
        CustomerAccount(
            customer_id=customer_id,
            balance=88.5,
            plan_name="畅享套餐",
            plan_price=99.0,
            contract_expiry_date=date(2027, 12, 31),
        )
    )
    db.commit()


async def test_customer_reads_own_profile_with_account(db_client, db):
    """客户认证 → 200 + 客户资料 + 账户信息（余额/套餐名/合约到期）。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db)
    _create_account(db, customer.id)

    response = await db_client.get(
        "/customers/me",
        headers={"Authorization": f"Bearer {create_access_token(customer.id)}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == customer.id
    assert body["phone"] == "13800000101"  # 客户视角不脱敏（自己看自己）
    assert body["name"] == "张三"
    assert body["balance"] == 88.5
    assert body["plan_name"] == "畅享套餐"
    assert body["contract_expiry_date"] == "2027-12-31"


async def test_customer_me_404_without_account(db_client, db):
    """Customer 存在但无账户记录 → 404（不编造账户信息）。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db)

    response = await db_client.get(
        "/customers/me",
        headers={"Authorization": f"Bearer {create_access_token(customer.id)}"},
    )

    assert response.status_code == 404


async def test_customer_me_requires_auth(db_client, db):
    """无 token → 401（CurrentCustomer 守卫）。"""
    _create_customer(db)

    response = await db_client.get("/customers/me")

    assert response.status_code == 401


async def test_customer_me_rejects_agent_token(db_client, db):
    """坐席 token → 401（客户端点主体隔离）。"""
    from app.auth.security import create_agent_access_token
    from app.models import User

    agent = User(
        employee_id="A5002",
        password_hash=_hash_password("agent-pass"),
        name="坐席五",
    )
    db.add(agent)
    db.commit()

    response = await db_client.get(
        "/customers/me",
        headers={"Authorization": f"Bearer {create_agent_access_token(agent.id)}"},
    )

    assert response.status_code == 401
