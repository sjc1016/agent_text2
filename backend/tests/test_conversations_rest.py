"""B2 循环2：REST 会话列表 + 消息历史 + 鉴权边界。

验收标准（issue #7）：
  GET /conversations 返回当前用户会话列表；
  GET /conversations/{id}/messages 返回消息历史
  （PRD 依据：实现决策 › API 契约 / RESTful 端点；测试决策 › HTTP 集成 seam；US-1）

鉴权复用 B1 的 Authorization header Bearer（CurrentCustomer）。
"""

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


async def _login(db_client, db, phone: str = "13900000010", password: str = "svc12345"):
    """创建客户并登录，返回 (customer, access_token)。"""
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password(password))
    db.add(customer)
    db.commit()

    resp = await db_client.post(
        "/auth/login",
        json={"phone": phone, "service_password": password},
    )
    assert resp.status_code == 200
    return customer, resp.json()["access_token"]


async def test_list_conversations_unauthenticated_returns_401(db_client):
    response = await db_client.get("/conversations")
    assert response.status_code == 401


async def test_list_conversations_returns_only_own_conversations(db_client, db):
    from app.models import Conversation, Customer

    customer, token = await _login(db_client, db, phone="13900000011")
    # 他人客户（真实存在，满足 FK 约束）
    other_customer = Customer(phone="13900000014", service_password_hash=_hash_password("svc12345"))
    db.add(other_customer)
    db.commit()
    # 自己的会话
    db.add(Conversation(customer_id=customer.id, status="authenticated"))
    # 他人的会话
    db.add(Conversation(customer_id=other_customer.id, status="authenticated"))
    db.commit()

    response = await db_client.get(
        "/conversations",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["customer_id"] == customer.id


async def test_get_messages_unauthenticated_returns_401(db_client, db):
    from app.models import Conversation

    conv = Conversation(customer_id=None, status="unauthenticated")
    db.add(conv)
    db.commit()

    response = await db_client.get(f"/conversations/{conv.id}/messages")
    assert response.status_code == 401


async def test_get_messages_returns_history_ordered(db_client, db):
    from app.models import Conversation, Message

    customer, token = await _login(db_client, db, phone="13900000012")
    conv = Conversation(customer_id=customer.id, status="authenticated")
    db.add(conv)
    db.flush()
    # 按创建顺序播种多条消息（不同来源）
    db.add(Message(conversation_id=conv.id, source="user", content="第一条"))
    db.add(Message(conversation_id=conv.id, source="assistant", content="第二条"))
    db.add(Message(conversation_id=conv.id, source="system", content="第三条"))
    db.commit()

    response = await db_client.get(
        f"/conversations/{conv.id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 3
    # 按 created_at 升序返回（消息历史顺序）
    contents = [m["content"] for m in items]
    assert contents == ["第一条", "第二条", "第三条"]


async def test_get_messages_other_customer_conversation_returns_404(db_client, db):
    from app.models import Conversation, Customer

    customer, token = await _login(db_client, db, phone="13900000013")
    # 他人客户（真实存在，满足 FK 约束）
    other_customer = Customer(phone="13900000015", service_password_hash=_hash_password("svc12345"))
    db.add(other_customer)
    db.commit()
    # 他人会话（不属于当前客户）
    other_conv = Conversation(customer_id=other_customer.id, status="authenticated")
    db.add(other_conv)
    db.commit()

    response = await db_client.get(
        f"/conversations/{other_conv.id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )

    # 不能查看他人会话消息；用 404 而非 403 避免泄露会话存在性
    assert response.status_code == 404


async def test_create_conversation_unauthenticated_returns_401(db_client):
    """未认证 POST /conversations → 401（会话创建需客户身份）。"""
    response = await db_client.post("/conversations")
    assert response.status_code == 401


async def test_create_conversation_returns_created(db_client, db):
    """认证客户 POST /conversations → 201 + ConversationOut（status=authenticated）。

    #24 UI-C-3 集成切片：对话页需要会话承载消息流（PRD › API 契约 /conversations 会话 CRUD）。
    """
    customer, token = await _login(db_client, db, phone="13900000016")

    response = await db_client.post(
        "/conversations",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["customer_id"] == customer.id
    assert payload["status"] == "authenticated"
    assert isinstance(payload["id"], int)
    assert isinstance(payload["created_at"], str)

    # 会话已持久化，列表可见（会话 CRUD）
    listed = await db_client.get(
        "/conversations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert any(item["id"] == payload["id"] for item in listed.json())
