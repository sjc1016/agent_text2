"""B13 循环2（issue #53 AC2）：客户读取自身站内通知列表（US-14）。

验收标准（issue #53 AC2）：
  客户认证可读取自身站内通知列表（GET /notifications：按时间倒序，
  含未读标记；未认证 → 401）
  （PRD 依据：实现决策 › API 契约（RESTful 端点）；
              用户故事 US-14（查看工单状态与站内通知））

行为：
  - 客户认证 → 200 + 通知列表（按时间倒序，含未读 read 标记）。
  - 仅返回当前客户的通知（主体隔离：他客户通知不可见）。
  - 未认证（无 token）→ 401（CurrentCustomer 守卫）。
"""

from datetime import datetime, timezone

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


def _create_ticket(db, customer_id: int, content: str = "办理 10G 流量加装包"):
    from app.models import Conversation, Ticket
    from app.models.ticket import TicketType

    conversation = Conversation(customer_id=customer_id, status="authenticated")
    db.add(conversation)
    db.flush()
    ticket = Ticket(
        conversation_id=conversation.id,
        ticket_type=TicketType.TRANSACTION,
        status="pending",
        content=content,
        creator_type="customer",
        creator_id=customer_id,
        customer_id=customer_id,
    )
    db.add(ticket)
    db.commit()
    return ticket


def _create_notification(
    db,
    ticket_id: int,
    customer_id: int,
    message: str,
    *,
    read: bool = False,
    created_at: datetime | None = None,
):
    from app.models import Notification

    notification = Notification(
        ticket_id=ticket_id,
        customer_id=customer_id,
        message=message,
        read=read,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(notification)
    db.commit()
    return notification


def _customer_token(customer) -> str:
    from app.auth.security import create_access_token

    return create_access_token(customer.id)


async def test_customer_reads_own_notifications_desc(db_client, db):
    """客户认证 → 200 + 通知列表（时间倒序，含未读 read 标记）。"""
    customer = _create_customer(db)
    ticket = _create_ticket(db, customer.id)
    _create_notification(
        db,
        ticket.id,
        customer.id,
        "您的办理工单已生效",
        created_at=datetime(2026, 8, 3, 2, 0, 0, tzinfo=timezone.utc),
    )
    _create_notification(
        db,
        ticket.id,
        customer.id,
        "您的办理工单已派单",
        read=True,
        created_at=datetime(2026, 8, 3, 2, 30, 0, tzinfo=timezone.utc),
    )

    response = await db_client.get(
        "/notifications",
        headers={"Authorization": f"Bearer {_customer_token(customer)}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert [n["message"] for n in body] == ["您的办理工单已派单", "您的办理工单已生效"]  # 倒序
    assert body[0]["read"] is True
    assert body[1]["read"] is False
    assert body[0]["ticket_id"] == ticket.id


async def test_notifications_are_scoped_to_current_customer(db_client, db):
    """主体隔离：仅返回当前客户的通知，他客户通知不可见。"""
    customer = _create_customer(db, phone="13800000092")
    other = _create_customer(db, phone="13800000093")
    ticket = _create_ticket(db, customer.id)
    _create_notification(db, ticket.id, customer.id, "我的通知")
    other_ticket = _create_ticket(db, other.id, content="他人工单")
    _create_notification(db, other_ticket.id, other.id, "他人通知")

    response = await db_client.get(
        "/notifications",
        headers={"Authorization": f"Bearer {_customer_token(customer)}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert [n["message"] for n in body] == ["我的通知"]


async def test_notifications_requires_auth(db_client, db):
    """未认证（无 token）→ 401。"""
    response = await db_client.get("/notifications")

    assert response.status_code == 401
