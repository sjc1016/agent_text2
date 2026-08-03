"""B14 循环1（issue #55 AC1）：GET /agents/tickets 坐席全局工单列表（US-27）。

验收标准（issue #55 AC1）：
  坐席可读全局工单列表（GET /agents/tickets：全部工单，created_at 倒序，
  customer_phone 脱敏；未认证 → 401）
  （PRD 依据：实现决策 › API 契约（RESTful 端点）；用户故事 US-27）

行为：
  - 坐席认证 → 200 + 全部工单（含 skill_group / 脱敏号码 / creator 信息）。
  - created_at 倒序（同 created_at 按 id 倒序，新单在前）。
  - 无 token → 401；客户 token → 401（坐席端点主体隔离）。
"""

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_agent(db, employee_id: str = "A6001"):
    from app.models import User

    agent = User(
        employee_id=employee_id,
        password_hash=_hash_password("agent-pass"),
        name="坐席六",
    )
    db.add(agent)
    db.commit()
    return agent


def _agent_token(agent) -> str:
    from app.auth.security import create_agent_access_token

    return create_agent_access_token(agent.id)


def _create_customer(db, phone: str = "13800000601"):
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


async def test_agent_lists_all_tickets(db_client, db):
    """坐席认证 → 200 + 全部工单（跨会话汇总，含脱敏号码与技能组）。"""
    from datetime import datetime, timedelta, timezone

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
        creator_type="agent",
        creator_id=agent.id,
        customer_id=customer.id,
    )
    t1.skill_group = "故障报修组"
    # 显式时间保证倒序断言稳定（server_default 同秒无区分）
    base = datetime.now(timezone.utc)
    t1.created_at = base - timedelta(minutes=10)
    t2.created_at = base
    db.commit()

    response = await db_client.get(
        "/agents/tickets",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
    )

    assert response.status_code == 200
    items = response.json()
    assert [item["id"] for item in items] == [t2.id, t1.id]  # created_at 倒序
    first = items[0]
    assert first["conversation_id"] == conv.id
    assert first["ticket_type"] == "transaction"
    assert first["creator_type"] == "agent"
    assert first["customer_phone"] == "138****0601"  # 脱敏（13800000601）
    assert items[1]["skill_group"] == "故障报修组"


async def test_agent_lists_tickets_orders_by_id_tiebreak(db_client, db):
    """同 created_at 时按 id 倒序（新单在前）。"""
    from app.ticket.service import create_ticket

    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    t1 = create_ticket(
        db,
        conversation_id=conv.id,
        ticket_type="ticketing",
        content="报修A",
        creator_type="customer",
        customer_id=customer.id,
    )
    t2 = create_ticket(
        db,
        conversation_id=conv.id,
        ticket_type="ticketing",
        content="报修B",
        creator_type="customer",
        customer_id=customer.id,
    )
    db.commit()

    response = await db_client.get(
        "/agents/tickets",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
    )

    assert response.status_code == 200
    items = response.json()
    assert [item["id"] for item in items] == [t2.id, t1.id]


async def test_agent_lists_tickets_requires_auth(db_client, db):
    """无 token → 401。"""
    response = await db_client.get("/agents/tickets")
    assert response.status_code == 401


async def test_agent_lists_tickets_rejects_customer_token(db_client, db):
    """客户 access token → 401（坐席端点主体隔离）。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db)
    customer_token = create_access_token(customer.id)

    response = await db_client.get(
        "/agents/tickets", headers={"Authorization": f"Bearer {customer_token}"}
    )

    assert response.status_code == 401


async def _ticketing_ticket(db, conv, content: str = "宽带故障报修"):
    from app.ticket.service import create_ticket

    ticket = create_ticket(
        db,
        conversation_id=conv.id,
        ticket_type="ticketing",
        content=content,
        creator_type="customer",
        customer_id=conv.customer_id,
    )
    db.commit()
    return ticket


async def test_agent_dispatches_ticket(db_client, db):
    """坐席派单（US-24）：工单类 pending → dispatched（含技能组 + 通知落库）。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    ticket = await _ticketing_ticket(db, conv)

    response = await db_client.post(
        f"/agents/tickets/{ticket.id}/dispatch?skill_group=故障报修组",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "dispatched"
    assert body["skill_group"] == "故障报修组"
    # 派单触发站内通知（工单类派单，CONTEXT › 通知）
    from app.models import Notification

    notifications = db.query(Notification).filter(Notification.ticket_id == ticket.id).all()
    assert len(notifications) == 1


async def test_agent_dispatches_without_skill_group(db_client, db):
    """派单可不带技能组（可选字段）。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    ticket = await _ticketing_ticket(db, conv)

    response = await db_client.post(
        f"/agents/tickets/{ticket.id}/dispatch",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "dispatched"
    assert response.json()["skill_group"] is None


async def test_agent_closes_ticket(db_client, db):
    """坐席关闭（US-24）：工单类 awaiting_confirmation → closed（通知落库）。"""
    from app.ticket.service import transition_ticket_status

    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    ticket = await _ticketing_ticket(db, conv)
    for status in ("dispatched", "in_progress", "awaiting_confirmation"):
        transition_ticket_status(db, ticket, status)
    db.commit()

    response = await db_client.post(
        f"/agents/tickets/{ticket.id}/close",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
        json={},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "closed"
    from app.models import Notification

    notifications = db.query(Notification).filter(Notification.ticket_id == ticket.id).all()
    assert len(notifications) == 1


async def test_agent_cancels_ticket(db_client, db):
    """坐席取消（US-24）：非终态 → cancelled（不触发通知）。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    ticket = await _ticketing_ticket(db, conv)

    response = await db_client.post(
        f"/agents/tickets/{ticket.id}/cancel",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
        json={},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    from app.models import Notification

    notifications = db.query(Notification).filter(Notification.ticket_id == ticket.id).all()
    assert len(notifications) == 0


async def test_agent_ticket_transition_rejects_illegal(db_client, db):
    """非法转换 → 422 状态不变（工单类 pending 不能直接 closed）。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    ticket = await _ticketing_ticket(db, conv)

    response = await db_client.post(
        f"/agents/tickets/{ticket.id}/close",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
        json={},
    )

    assert response.status_code == 422
    db.refresh(ticket)
    assert ticket.status.value == "pending"


async def test_agent_ticket_transition_404_for_missing(db_client, db):
    """工单不存在 → 404。"""
    agent = _create_agent(db)
    response = await db_client.post(
        "/agents/tickets/9999/close",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
        json={},
    )
    assert response.status_code == 404


async def test_agent_ticket_transition_requires_auth(db_client, db):
    """无 token → 401。"""
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    ticket = await _ticketing_ticket(db, conv)

    response = await db_client.post(f"/agents/tickets/{ticket.id}/cancel", json={})
    assert response.status_code == 401


async def test_agent_gets_ticket_detail(db_client, db):
    """坐席读工单详情（US-28）：基本信息 + 脱敏号码 + 技能组 + 创建者。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    ticket = await _ticketing_ticket(db, conv)
    ticket.skill_group = "投诉处理组"
    db.commit()

    response = await db_client.get(
        f"/agents/tickets/{ticket.id}",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == ticket.id
    assert body["conversation_id"] == conv.id
    assert body["ticket_type"] == "ticketing"
    assert body["status"] == "pending"
    assert body["content"] == "宽带故障报修"
    assert body["skill_group"] == "投诉处理组"
    assert body["customer_phone"] == "138****0601"  # 脱敏（13800000601）
    assert body["customer_id"] == customer.id
    assert isinstance(body["created_at"], str)


async def test_agent_gets_ticket_detail_404_for_missing(db_client, db):
    """工单不存在 → 404。"""
    agent = _create_agent(db)
    response = await db_client.get(
        "/agents/tickets/9999", headers={"Authorization": f"Bearer {_agent_token(agent)}"}
    )
    assert response.status_code == 404


async def test_agent_gets_ticket_detail_requires_auth(db_client, db):
    """无 token → 401。"""
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    ticket = await _ticketing_ticket(db, conv)

    response = await db_client.get(f"/agents/tickets/{ticket.id}")
    assert response.status_code == 401


async def test_agent_gets_conversation_view(db_client, db):
    """坐席读单会话视图（US-21）：status/脱敏号码/handoff_reason/created_at。"""
    from app.models import Conversation

    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = Conversation(
        customer_id=customer.id, status="handed_off", handoff_reason="explicit_request"
    )
    db.add(conv)
    db.commit()

    response = await db_client.get(
        f"/agents/conversations/{conv.id}",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == conv.id
    assert body["status"] == "handed_off"
    assert body["customer_id"] == customer.id
    assert body["customer_phone"] == "138****0601"  # 脱敏（13800000601）
    assert body["handoff_reason"] == "explicit_request"
    assert isinstance(body["created_at"], str)


async def test_agent_gets_conversation_view_404_for_non_handed_off(db_client, db):
    """会话非 handed_off → 404（坐席不可见）。"""
    from app.models import Conversation

    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = Conversation(customer_id=customer.id, status="authenticated")
    db.add(conv)
    db.commit()

    response = await db_client.get(
        f"/agents/conversations/{conv.id}",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
    )

    assert response.status_code == 404


async def test_agent_gets_conversation_view_404_for_missing(db_client, db):
    """会话不存在 → 404。"""
    agent = _create_agent(db)
    response = await db_client.get(
        "/agents/conversations/9999", headers={"Authorization": f"Bearer {_agent_token(agent)}"}
    )
    assert response.status_code == 404


async def test_agent_gets_conversation_view_requires_auth(db_client, db):
    """无 token → 401。"""
    response = await db_client.get("/agents/conversations/1")
    assert response.status_code == 401


async def test_agent_gets_conversation_view_rejects_customer_token(db_client, db):
    """客户 access token → 401（坐席端点主体隔离）。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db)
    customer_token = create_access_token(customer.id)

    response = await db_client.get(
        "/agents/conversations/1", headers={"Authorization": f"Bearer {customer_token}"}
    )

    assert response.status_code == 401
