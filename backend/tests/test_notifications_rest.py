"""B13 循环2（issue #53 AC2）：客户读取自身站内通知列表（US-14）。

验收标准（issue #53 AC2）：
  客户认证可读取自身站内通知列表（GET /notifications：
  按时间倒序，含未读标记；未认证 → 401）
  （PRD 依据：实现决策 › API 契约（RESTful 端点）；
              用户故事 US-14（查看工单状态与站内通知））

行为：
  - 客户认证 → 200 + 通知列表（按 created_at 倒序；含 read 未读标记），
    供 UI-C-4 通知预览条冷启动数据源（WS notification.push 只覆盖实时）。
  - 主体隔离：只返回当前客户的通知，他人通知不可见。
  - 无 token / 坐席 token → 401。
"""

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_customer(db, phone: str = "13800000202"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password("x"), name="李四")
    db.add(customer)
    db.commit()
    return customer


def _create_ticket(db, customer_id: int) -> int:
    from app.models import Conversation
    from app.models.ticket import Ticket, TicketType

    conv = Conversation(customer_id=customer_id, status="authenticated")
    db.add(conv)
    db.commit()
    ticket = Ticket(
        conversation_id=conv.id,
        ticket_type=TicketType.TRANSACTION,
        content="套餐变更",
        customer_id=customer_id,
        creator_type="customer",
        creator_id=customer_id,
    )
    db.add(ticket)
    db.commit()
    return ticket.id


def _create_notification(
    db, ticket_id: int, customer_id: int, message: str, read: bool = False
) -> None:
    from app.models import Notification

    db.add(
        Notification(
            ticket_id=ticket_id,
            customer_id=customer_id,
            message=message,
            read=read,
        )
    )
    db.commit()


async def test_customer_lists_own_notifications_desc(db_client, db):
    """客户认证 → 200 + 通知列表（时间倒序、含 read 标记）。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db)
    ticket_id = _create_ticket(db, customer.id)
    _create_notification(db, ticket_id, customer.id, "您的办理工单已生效", read=True)
    _create_notification(db, ticket_id, customer.id, "您的工单已派单")

    response = await db_client.get(
        "/notifications",
        headers={"Authorization": f"Bearer {create_access_token(customer.id)}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    # 时间倒序：后创建的「已派单」在前
    assert body[0]["message"] == "您的工单已派单"
    assert body[0]["read"] is False
    assert body[0]["ticket_id"] == ticket_id
    assert body[1]["message"] == "您的办理工单已生效"
    assert body[1]["read"] is True
    assert body[0]["created_at"] >= body[1]["created_at"]


async def test_notifications_isolated_per_customer(db_client, db):
    """主体隔离：只返回当前客户的通知，他人通知不可见。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db, phone="13800000202")
    other = _create_customer(db, phone="13800000303")
    my_ticket = _create_ticket(db, customer.id)
    other_ticket = _create_ticket(db, other.id)
    _create_notification(db, my_ticket, customer.id, "我的通知")
    _create_notification(db, other_ticket, other.id, "他人的通知")

    response = await db_client.get(
        "/notifications",
        headers={"Authorization": f"Bearer {create_access_token(customer.id)}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["message"] == "我的通知"


async def test_notifications_requires_auth(db_client, db):
    """无 token → 401（CurrentCustomer 守卫）。"""
    response = await db_client.get("/notifications")

    assert response.status_code == 401
