"""B12 循环1（issue #44 AC1）：坐席读取会话消息历史（US-21）。

验收标准（issue #44 AC1）：
  坐席认证可读取会话消息历史（GET /agents/conversations/{id}/messages；
  handed_off 会话；客户 token → 401）
  （PRD 依据：实现决策 › API 契约（RESTful 端点 /conversations/{id}/messages）；
              用户故事 US-21（接入并查看会话历史与客户资料））

行为：
  - 坐席认证访问 handed_off 会话 → 200 + 消息历史（按 created_at 升序，
    与客户侧 /conversations/{id}/messages 同构，复用 MessageOut 形状）。
  - 客户 access token 访问 → 401（主体隔离，get_current_agent 拒绝 access）。
  - 会话不存在 / 非 handed_off（转回或未转接）→ 404（不泄露存在性）。
"""

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_agent(db, employee_id: str = "A5001"):
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


def _create_customer(db, phone: str = "13800000091"):
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


def _seed_messages(db, conv, contents: list[str]) -> None:
    """按序写入 user/assistant 交替消息（B12：handed_off 会话对话流）。"""
    from app.conversation.service import create_message

    for index, content in enumerate(contents):
        source = "user" if index % 2 == 0 else "assistant"
        db.add(create_message(db, conv.id, source, content))
    db.commit()


async def test_agent_reads_handed_off_conversation_messages(db_client, db):
    """坐席认证 → 200 + handed_off 会话消息历史（升序，四类来源透传）。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    _seed_messages(db, conv, ["套餐怎么改？", "您好，为您查询当前套餐", "帮我报修宽带"])

    response = await db_client.get(
        f"/agents/conversations/{conv.id}/messages",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
    )

    assert response.status_code == 200
    items = response.json()
    assert [item["content"] for item in items] == [
        "套餐怎么改？",
        "您好，为您查询当前套餐",
        "帮我报修宽带",
    ]
    assert [item["source"] for item in items] == ["user", "assistant", "user"]
    assert all(item["conversation_id"] == conv.id for item in items)
    assert all(isinstance(item["created_at"], str) for item in items)


async def test_agent_messages_rejects_customer_token(db_client, db):
    """客户 access token → 401（坐席端点主体隔离）。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    customer_token = create_access_token(customer.id)

    response = await db_client.get(
        f"/agents/conversations/{conv.id}/messages",
        headers={"Authorization": f"Bearer {customer_token}"},
    )

    assert response.status_code == 401


async def test_agent_messages_requires_auth(db_client, db):
    """无 token → 401。"""
    response = await db_client.get("/agents/conversations/1/messages")
    assert response.status_code == 401


async def test_agent_messages_404_for_missing_conversation(db_client, db):
    """会话不存在 → 404（不泄露存在性）。"""
    agent = _create_agent(db)

    response = await db_client.get(
        "/agents/conversations/9999/messages",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
    )

    assert response.status_code == 404


async def test_agent_messages_404_for_non_handed_off_conversation(db_client, db):
    """会话存在但非 handed_off（authenticated）→ 404（坐席不可见）。"""
    agent = _create_agent(db)
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id, status="authenticated")

    response = await db_client.get(
        f"/agents/conversations/{conv.id}/messages",
        headers={"Authorization": f"Bearer {_agent_token(agent)}"},
    )

    assert response.status_code == 404
