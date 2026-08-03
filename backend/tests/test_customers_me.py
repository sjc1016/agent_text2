"""B13 循环1（issue #53 AC1）：客户读取自身账户资料（US-17）。

验收标准（issue #53 AC1）：
  客户认证可读取自身账户资料（GET /customers/me：话费余额/套餐名/合约到期；
  未认证 → 401；复用 B12 坐席侧同一数据源）
  （PRD 依据：实现决策 › API 契约（RESTful 端点，/customers/me）；
              用户故事 US-17（查看会话历史与账号信息））

行为：
  - 客户认证 → 200 + 账户资料（话费余额/套餐名/合约到期，复用
    get_customer_profile 同一数据源；phone 完整号码——客户读自身资料）。
  - 未认证（无 token / 无效 token）→ 401（CurrentCustomer 守卫）。
  - Customer 存在但无账户记录 → 404（与 B12 相同语义，不编造账户信息）。
"""

from datetime import date

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_customer(db, phone: str = "13800000092"):
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


def _customer_token(customer) -> str:
    from app.auth.security import create_access_token

    return create_access_token(customer.id)


async def test_customer_reads_own_profile_with_account(db_client, db):
    """客户认证 → 200 + 账户资料（余额/套餐名/合约到期，复用 B12 同一数据源）。"""
    customer = _create_customer(db)
    _create_account(db, customer.id)

    response = await db_client.get(
        "/customers/me",
        headers={"Authorization": f"Bearer {_customer_token(customer)}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == customer.id
    assert body["phone"] == "13800000092"  # 客户读自身资料，完整号码（与 /auth/me 一致）
    assert body["name"] == "张三"
    assert body["balance"] == 88.5
    assert body["plan_name"] == "畅享套餐"
    assert body["contract_expiry_date"] == "2027-12-31"


async def test_customers_me_requires_auth(db_client, db):
    """未认证（无 token）→ 401。"""
    customer = _create_customer(db)
    _create_account(db, customer.id)

    response = await db_client.get("/customers/me")

    assert response.status_code == 401


async def test_customers_me_404_without_account(db_client, db):
    """Customer 存在但无账户记录 → 404（与 B12 相同语义，不编造账户信息）。"""
    customer = _create_customer(db)

    response = await db_client.get(
        "/customers/me",
        headers={"Authorization": f"Bearer {_customer_token(customer)}"},
    )

    assert response.status_code == 404
