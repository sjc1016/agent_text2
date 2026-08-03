"""B12 循环2（issue #44 AC2）：坐席读取客户资料 + 账户信息（US-21）。

验收标准（issue #44 AC2）：
  坐席认证可读取客户资料 + 账户信息（GET /agents/customers/{id}：
  话费余额/套餐名/合约到期；访客/无账户 → 404；敏感数据访问写审计日志）
  （PRD 依据：实现决策 › API 契约（RESTful 端点）；
              用户故事 US-21（接入并查看会话历史与客户资料）；
              CONTEXT › 审计日志（用户敏感数据访问须留痕））

行为：
  - 坐席认证 → 200 + 客户资料（号码脱敏、名称、认证态）+ 账户信息
    （话费余额/套餐名/合约到期，复用 inquiry 数据源 CustomerAccount）。
  - Customer 不存在（访客/无效 id）→ 404；Customer 存在但无账户记录 → 404。
  - 客户 access token / 无 token → 401（主体隔离）。
  - 敏感数据访问写审计日志（agent.customer_profile_access）。
"""

from datetime import date

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_agent(db, employee_id: str = "A5002"):
    from app.models import User

    agent = User(
        employee_id=employee_id,
        password_hash=_hash_password("agent-pass"),
        name="坐席五",
    )
    db.add(agent)
    db.commit()
    return agent


def _agent_token(agent) -> str:
    from app.auth.security import create_agent_access_token

    return create_agent_access_token(agent.id)


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


async def test_agent_reads_customer_profile_with_account(db_client, db):
    """坐席认证 → 200 + 客户资料（脱敏号码/名称/认证态）+ 账户信息（余额/套餐/合约到期）。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    _create_account(db, customer.id)

    response = await db_client.get(
        f"/agents/customers/{customer.id}",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == customer.id
    assert body["phone"] == "138****0092"  # 脱敏
    assert body["name"] == "张三"
    assert body["authenticated"] is True
    assert body["balance"] == 88.5
    assert body["plan_name"] == "畅享套餐"
    assert body["contract_expiry_date"] == "2027-12-31"


async def test_agent_profile_writes_audit_log(db_client, db):
    """敏感数据访问写审计日志（agent.customer_profile_access）。"""
    from sqlalchemy import select

    from app.models import AuditLog

    agent = _create_agent(db)
    customer = _create_customer(db)
    _create_account(db, customer.id)

    await db_client.get(
        f"/agents/customers/{customer.id}",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
    )

    db.expire_all()
    logs = (
        db.execute(select(AuditLog).where(AuditLog.action == "agent.customer_profile_access"))
        .scalars()
        .all()
    )
    assert len(logs) == 1
    assert logs[0].actor_type == "agent"
    assert logs[0].actor_id == agent.id
    assert logs[0].detail.get("customer_id") == customer.id


async def test_agent_profile_404_for_missing_customer(db_client, db):
    """Customer 不存在（访客/无效 id）→ 404。"""
    agent = _create_agent(db)

    response = await db_client.get(
        "/agents/customers/9999",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
    )

    assert response.status_code == 404


async def test_agent_profile_404_without_account(db_client, db):
    """Customer 存在但无账户记录 → 404（不编造账户信息）。"""
    agent = _create_agent(db)
    customer = _create_customer(db)

    response = await db_client.get(
        f"/agents/customers/{customer.id}",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
    )

    assert response.status_code == 404


async def test_agent_profile_rejects_customer_token(db_client, db):
    """客户 access token → 401（坐席端点主体隔离）。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db)
    _create_account(db, customer.id)
    customer_token = create_access_token(customer.id)

    response = await db_client.get(
        f"/agents/customers/{customer.id}",
        headers={"Authorization": f"Bearer {customer_token}"},
    )

    assert response.status_code == 401
