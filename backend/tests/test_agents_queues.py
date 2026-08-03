"""B9 循环6：GET /agents/queues 待接入队列（US-20）。

验收标准（issue #15）：
  GET /agents/queues 返回待接入 Handoff 会话列表
  （PRD 依据：PRD 实现决策 › API 契约 /agents/queues；
              PRD 测试决策 › HTTP 集成 seam；用户故事 US-20）

「待接入」= 会话状态 handed_off 且 agent_id 为空（未被任何坐席接入）。
队列项含：conversation_id、状态、创建时间、customer_id、脱敏手机号（138****0001）、
最后一条用户消息。
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


def _create_conversation(db, customer_id, status: str = "handed_off", agent_id: int | None = None):
    from app.models import Conversation

    conv = Conversation(
        customer_id=customer_id,
        status=status,
        agent_id=agent_id,
    )
    db.add(conv)
    db.commit()
    return conv


def _create_message(db, conversation_id: int, source: str, content: str):
    from app.models import Message

    msg = Message(conversation_id=conversation_id, source=source, content=content)
    db.add(msg)
    db.commit()
    return msg


async def test_queues_returns_pending_handoff_conversations(db_client, db):
    """handed_off 未接入会话 → 200 + 队列项（脱敏手机号 + 最后用户消息）。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    _create_message(db, conv.id, "user", "我想办理宽带提速")
    _create_message(db, conv.id, "assistant", "好的，已为您转接人工")

    response = await db_client.get(
        "/agents/queues", headers={"Authorization": f"Bearer {_agent_token(agent)}"}
    )

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    item = items[0]
    assert item["conversation_id"] == conv.id
    assert item["status"] == "handed_off"
    assert item["customer_id"] == customer.id
    assert item["customer_phone"] == "138****0001"
    assert item["last_user_message"] == "我想办理宽带提速"
    assert isinstance(item["created_at"], str)


async def test_queues_excludes_taken_over_conversations(db_client, db):
    """已被坐席接入（agent_id 非空）的会话不在队列中。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    _create_conversation(db, customer.id, agent_id=agent.id)

    response = await db_client.get(
        "/agents/queues", headers={"Authorization": f"Bearer {_agent_token(agent)}"}
    )

    assert response.status_code == 200
    assert response.json() == []


async def test_queues_excludes_non_handed_off_conversations(db_client, db):
    """非 handed_off 状态（authenticated）不在队列中。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    _create_conversation(db, customer.id, status="authenticated")

    response = await db_client.get(
        "/agents/queues", headers={"Authorization": f"Bearer {_agent_token(agent)}"}
    )

    assert response.status_code == 200
    assert response.json() == []


async def test_queues_includes_handoff_reason(db_client, db):
    """B11：队列项含转接原因（来自会话 handoff_reason，PRD queue 页转接原因 Caption）。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    conv.handoff_reason = "explicit_request"
    db.commit()

    response = await db_client.get(
        "/agents/queues", headers={"Authorization": f"Bearer {_agent_token(agent)}"}
    )

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["reason"] == "explicit_request"


async def test_queues_reason_null_when_no_handoff_reason(db_client, db):
    """B11：未持久化转接原因的会话，队列项 reason 为 null。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    _create_conversation(db, customer.id)

    response = await db_client.get(
        "/agents/queues", headers={"Authorization": f"Bearer {_agent_token(agent)}"}
    )

    assert response.status_code == 200
    assert response.json()[0]["reason"] is None


async def test_queues_requires_agent_auth(db_client, db):
    """无 token → 401。"""
    response = await db_client.get("/agents/queues")
    assert response.status_code == 401


async def test_queues_rejects_customer_token(db_client, db):
    """客户 access token 不能访问坐席队列（主体隔离）。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db)
    customer_token = create_access_token(customer.id)

    response = await db_client.get(
        "/agents/queues", headers={"Authorization": f"Bearer {customer_token}"}
    )

    assert response.status_code == 401
