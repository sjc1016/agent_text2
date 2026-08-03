"""B12 循环3（issue #44 AC3）：坐席查询会话工单列表 + 创建工单（US-23）。

验收标准（issue #44 AC3）：
  坐席认证可查询会话所属工单列表（GET /agents/conversations/{id}/tickets）
  + 创建工单（POST /agents/tickets，creator_type=agent）
  （PRD 依据：实现决策 › API 契约（RESTful 端点 /tickets）；
              用户故事 US-23（建单：坐席在会话中为客户创建工单））

行为：
  - GET：坐席认证访问 handed_off 会话 → 200 + 该会话全部工单（复用 TicketOut 形状）。
  - GET：会话不存在 / 非 handed_off → 404；客户 token / 无 token → 401。
  - POST：坐席认证 → 201 + 工单（creator_type=agent，creator_id=坐席，
    customer_id=会话所属客户，pending 入队）。
  - POST：会话不存在 / 非 handed_off → 404（坐席仅能在接入的转接会话建单）。
"""

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_agent(db, employee_id: str = "A5003"):
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


def _create_customer(db, phone: str = "13800000093"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password("x"))
    db.add(customer)
    db.commit()
    return customer


def _create_conversation(db, customer_id: int, status: str = "handed_off"):
    from app.models import Conversation

    conv = Conversation(customer_id=customer_id, status=status)
    db.add(conv)
    db.commit()
    return conv


async def test_agent_lists_conversation_tickets(db_client, db):
    """坐席认证 → 200 + 会话所属工单列表（含办理类与工单类）。"""
    from app.ticket.service import create_ticket

    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    t1 = create_ticket(
        db,
        conversation_id=conv.id,
        ticket_type="ticketing",
        content="宽带故障报修",
        creator_type="customer",
        customer_id=customer.id,
    )
    t2 = create_ticket(
        db,
        conversation_id=conv.id,
        ticket_type="transaction",
        content="办理套餐变更",
        creator_type="customer",
        customer_id=customer.id,
    )
    db.commit()

    response = await db_client.get(
        f"/agents/conversations/{conv.id}/tickets",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
    )

    assert response.status_code == 200
    items = response.json()
    assert {item["id"] for item in items} == {t1.id, t2.id}
    assert all(item["conversation_id"] == conv.id for item in items)
    assert {item["ticket_type"] for item in items} == {"ticketing", "transaction"}


async def test_agent_lists_tickets_404_for_non_handed_off(db_client, db):
    """会话非 handed_off → 404（坐席不可见）。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id, status="authenticated")

    response = await db_client.get(
        f"/agents/conversations/{conv.id}/tickets",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
    )

    assert response.status_code == 404


async def test_agent_lists_tickets_rejects_customer_token(db_client, db):
    """客户 access token → 401（坐席端点主体隔离）。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    customer_token = create_access_token(customer.id)

    response = await db_client.get(
        f"/agents/conversations/{conv.id}/tickets",
        headers={"Authorization": f"Bearer {customer_token}"},
    )

    assert response.status_code == 401


async def test_agent_creates_ticket(db_client, db):
    """坐席认证 → 201 + 工单（creator_type=agent，creator_id=坐席，customer_id=会话客户）。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)

    response = await db_client.post(
        "/agents/tickets",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
        json={
            "conversation_id": conv.id,
            "ticket_type": "ticketing",
            "content": "客户报修宽带线路故障",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["conversation_id"] == conv.id
    assert body["ticket_type"] == "ticketing"
    assert body["status"] == "pending"
    assert body["creator_type"] == "agent"
    assert body["creator_id"] == agent.id
    assert body["customer_id"] == customer.id


async def test_agent_creates_ticket_404_for_non_handed_off(db_client, db):
    """会话非 handed_off → 404（坐席仅能在接入的转接会话建单）。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id, status="authenticated")

    response = await db_client.post(
        "/agents/tickets",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
        json={
            "conversation_id": conv.id,
            "ticket_type": "ticketing",
            "content": "客户报修",
        },
    )

    assert response.status_code == 404


async def test_agent_creates_ticket_rejects_customer_token(db_client, db):
    """客户 access token → 401。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    customer_token = create_access_token(customer.id)

    response = await db_client.post(
        "/agents/tickets",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={
            "conversation_id": conv.id,
            "ticket_type": "ticketing",
            "content": "客户报修",
        },
    )

    assert response.status_code == 401
