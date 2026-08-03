"""B12 循环4（issue #44 AC4）：坐席引导服务密码复核并单步执行（US-25）。

验收标准（issue #44 AC4）：
  坐席认证可引导服务密码复核并单步执行
  （POST /agents/transactions/{ticket_id}/execute：service_password 校验失败
  → 401/422 状态不变；成功 → Processing → Effective 并写审计）
  （PRD 依据：实现决策 › 办理执行复核（Transaction Re-auth）；
              用户故事 US-25（执行复核：坐席引导用户再次输入服务密码））

行为：
  - 坐席认证 + 正确 service_password → 200 + 工单 effective + 审计
    （transaction.execute.agent）。
  - 错误 service_password → 401，工单状态不变（仍 pending）。
  - 工单不存在 → 404；非办理类工单 → 422；访客工单（无客户可复核）→ 401。
  - 客户 access token / 无 token → 401（主体隔离）。
"""

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_agent(db, employee_id: str = "A5004"):
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


def _create_customer(db, phone: str = "13800000094", password: str = "svc-pass-123"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password(password), name="李四")
    db.add(customer)
    db.commit()
    return customer


def _create_conversation(db, customer_id: int | None, status: str = "authenticated"):
    from app.models import Conversation

    conv = Conversation(customer_id=customer_id, status=status)
    db.add(conv)
    db.commit()
    return conv


def _create_transaction_ticket(db, conv, customer_id: int | None):
    from app.ticket.service import create_ticket

    ticket = create_ticket(
        db,
        conversation_id=conv.id,
        ticket_type="transaction",
        content="办理套餐变更：畅享套餐",
        creator_type="customer",
        customer_id=customer_id,
    )
    db.commit()
    return ticket


async def test_agent_execute_with_valid_password(db_client, db):
    """坐席 + 正确服务密码 → 200 + effective + 审计（transaction.execute.agent）。"""
    from sqlalchemy import select

    from app.models import AuditLog

    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    ticket = _create_transaction_ticket(db, conv, customer.id)

    response = await db_client.post(
        f"/agents/transactions/{ticket.id}/execute",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
        json={"service_password": "svc-pass-123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == ticket.id
    assert body["status"] == "effective"

    db.expire_all()
    assert ticket.status.value == "effective"
    logs = (
        db.execute(select(AuditLog).where(AuditLog.action == "transaction.execute.agent"))
        .scalars()
        .all()
    )
    assert len(logs) == 1
    assert logs[0].actor_type == "agent"
    assert logs[0].actor_id == agent.id


async def test_agent_execute_with_wrong_password_unchanged(db_client, db):
    """错误服务密码 → 401，工单状态不变（仍 pending）。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    ticket = _create_transaction_ticket(db, conv, customer.id)

    response = await db_client.post(
        f"/agents/transactions/{ticket.id}/execute",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
        json={"service_password": "wrong-password"},
    )

    assert response.status_code == 401
    db.refresh(ticket)
    assert ticket.status.value == "pending"


async def test_agent_execute_404_for_missing_ticket(db_client, db):
    """工单不存在 → 404。"""
    agent = _create_agent(db)

    response = await db_client.post(
        "/agents/transactions/9999/execute",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
        json={"service_password": "svc-pass-123"},
    )

    assert response.status_code == 404


async def test_agent_execute_422_for_non_transaction_ticket(db_client, db):
    """非办理类工单 → 422（仅办理类可执行）。"""
    from app.ticket.service import create_ticket

    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    ticket = create_ticket(
        db,
        conversation_id=conv.id,
        ticket_type="ticketing",
        content="宽带故障报修",
        creator_type="customer",
        customer_id=customer.id,
    )
    db.commit()

    response = await db_client.post(
        f"/agents/transactions/{ticket.id}/execute",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
        json={"service_password": "svc-pass-123"},
    )

    assert response.status_code == 422


async def test_agent_execute_401_for_visitor_ticket(db_client, db):
    """访客工单（无客户可复核）→ 401（无法引导服务密码复核）。"""
    agent = _create_agent(db)
    conv = _create_conversation(db, None)
    ticket = _create_transaction_ticket(db, conv, None)

    response = await db_client.post(
        f"/agents/transactions/{ticket.id}/execute",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
        json={"service_password": "svc-pass-123"},
    )

    assert response.status_code == 401
    db.refresh(ticket)
    assert ticket.status.value == "pending"


async def test_agent_execute_rejects_customer_token(db_client, db):
    """客户 access token → 401（坐席端点主体隔离）。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    ticket = _create_transaction_ticket(db, conv, customer.id)
    customer_token = create_access_token(customer.id)

    response = await db_client.post(
        f"/agents/transactions/{ticket.id}/execute",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={"service_password": "svc-pass-123"},
    )

    assert response.status_code == 401
