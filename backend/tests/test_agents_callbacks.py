"""B11 循环4（issue #42 AC3）：GET /agents/callbacks 回呼请求工单列表（US-29）。

验收标准（issue #42 AC3）：
  新增 GET /agents/callbacks：坐席认证返回回呼请求工单列表（工单类 +
  内容前缀 [回呼请求] + dispatched），每项含工单 ID、会话 ID、客户脱敏号码、
  技能组、创建时间
  （PRD 依据：实现决策 › API 契约；用户故事 US-29；
              PRD queue 页 UI 设计描述：回呼请求独立分组 + 拨打按钮）

回呼请求 Ticket（B8 离线兜底）由 trigger_handoff/create_callback_ticket 创建：
工单类 + 内容前缀 [回呼请求] + 创建即派单（dispatched）+ skill_group。
"""

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_agent(db, employee_id: str = "A2001"):
    from app.models import User

    agent = User(
        employee_id=employee_id,
        password_hash=_hash_password("agent-pass"),
        name="坐席二",
    )
    db.add(agent)
    db.commit()
    return agent


def _agent_token(agent) -> str:
    from app.auth.security import create_agent_access_token

    return create_agent_access_token(agent.id)


def _create_customer(db, phone: str = "13800000001"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password("x"))
    db.add(customer)
    db.commit()
    return customer


def _create_conversation(db, customer_id, status: str = "handed_off"):
    from app.models import Conversation

    conv = Conversation(customer_id=customer_id, status=status)
    db.add(conv)
    db.commit()
    return conv


def _create_callback_ticket(db, conv):
    """直接构造回呼请求 Ticket（离线兜底产物：工单类 + [回呼请求] 前缀 + dispatched）。"""
    from app.handoff.service import create_callback_ticket
    from app.handoff.triggers import HandoffReason

    return create_callback_ticket(db, conv, HandoffReason.OUT_OF_SCOPE)


async def test_callbacks_returns_callback_tickets(db_client, db):
    """坐席认证 → 200 + 回呼请求工单列表（工单 ID/会话 ID/脱敏号码/技能组/创建时间）。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    ticket = _create_callback_ticket(db, conv)

    response = await db_client.get(
        "/agents/callbacks", headers={"Authorization": f"Bearer {_agent_token(agent)}"}
    )

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    item = items[0]
    assert item["ticket_id"] == ticket.id
    assert item["conversation_id"] == conv.id
    assert item["customer_id"] == customer.id
    assert item["customer_phone"] == "138****0001"  # 脱敏
    assert item["skill_group"] == "套餐业务组"
    assert "回呼请求" in item["content"]
    assert isinstance(item["created_at"], str)


async def test_callbacks_excludes_non_callback_tickets(db_client, db):
    """非回呼请求工单（普通工单类/办理类）不出现在列表。"""
    from app.ticket.service import create_ticket

    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)

    # 普通工单类工单（非 [回呼请求] 前缀）
    create_ticket(
        db,
        conversation_id=conv.id,
        ticket_type="ticketing",
        content="宽带故障报修",
        creator_type="customer",
        customer_id=customer.id,
    )
    db.commit()

    response = await db_client.get(
        "/agents/callbacks", headers={"Authorization": f"Bearer {_agent_token(agent)}"}
    )

    assert response.status_code == 200
    assert response.json() == []


async def test_callbacks_requires_agent_auth(db_client, db):
    """无 token → 401。"""
    response = await db_client.get("/agents/callbacks")
    assert response.status_code == 401


async def test_callbacks_rejects_customer_token(db_client, db):
    """客户 access token 不能访问回呼端点（主体隔离）。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db)
    customer_token = create_access_token(customer.id)

    response = await db_client.get(
        "/agents/callbacks", headers={"Authorization": f"Bearer {customer_token}"}
    )

    assert response.status_code == 401


async def test_callbacks_orders_by_created_at(db_client, db):
    """回呼请求工单按创建时间升序。"""
    from app.handoff.service import create_callback_ticket
    from app.handoff.triggers import HandoffReason
    from app.models import Conversation

    agent = _create_agent(db)
    customer = _create_customer(db)

    first = Conversation(customer_id=customer.id, status="handed_off")
    db.add(first)
    db.commit()
    t1 = create_callback_ticket(db, first, HandoffReason.OUT_OF_SCOPE)

    second = Conversation(customer_id=customer.id, status="handed_off")
    db.add(second)
    db.commit()
    t2 = create_callback_ticket(db, second, HandoffReason.EXPLICIT_REQUEST)

    response = await db_client.get(
        "/agents/callbacks", headers={"Authorization": f"Bearer {_agent_token(agent)}"}
    )

    assert response.status_code == 200
    ids = [item["ticket_id"] for item in response.json()]
    assert ids == [t1.id, t2.id]
