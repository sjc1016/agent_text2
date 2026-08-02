"""B7 循环6-7：WS ticket.update + notification.push 推送与通知持久化。

验收标准（issue #10）：
  Ticket 状态变化推送 ticket.update，办理生效/失败、工单派单/关闭推送 notification.push
  （PRD 依据：实现决策 › API 契约 / WebSocket 事件；
              测试决策 › WS 事件 seam；用户故事 US-14）

WS 事件 seam：pytest + TestClient WebSocket 连接客户，触发 REST PATCH 状态流转，
断言同一客户连接收到 ticket.update / notification.push（envelope {event, data}）。
"""

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_customer(db, phone: str = "13900000060", password: str = "svc12345"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password(password))
    db.add(customer)
    db.commit()
    return customer


def _create_ticket(db, customer, ticket_type: str = "transaction", status: str = "pending"):
    from app.models import Conversation, Ticket

    conv = Conversation(customer_id=customer.id, status="authenticated")
    db.add(conv)
    db.commit()
    ticket = Ticket(
        conversation_id=conv.id,
        ticket_type=ticket_type,
        status=status,
        content="套餐变更",
        customer_id=customer.id,
        creator_type="customer",
        creator_id=customer.id,
    )
    db.add(ticket)
    db.commit()
    return ticket


def test_ws_ticket_update_on_status_change(ws_client, db):
    """状态流转成功后，客户连接收到 ticket.update（含 old_status/new_status）。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db, phone="13900000061")
    token = create_access_token(customer.id)
    ticket = _create_ticket(db, customer)

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # accept 后 system.message
        resp = ws_client.patch(
            f"/tickets/{ticket.id}",
            json={"status": "processing"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        event = ws.receive_json()

    assert event["event"] == "ticket.update"
    payload = event["data"]
    assert payload["id"] == ticket.id
    assert payload["conversation_id"] == ticket.conversation_id
    assert payload["ticket_type"] == "transaction"
    assert payload["old_status"] == "pending"
    assert payload["status"] == "processing"
    assert isinstance(payload["changed_at"], str)


def test_ws_ticket_update_not_pushed_on_illegal_transition(ws_client, db):
    """非法流转（422）不推送 ticket.update（状态未变，无事件）。

    断言方式：合法流转后 WS 收到 ticket.update；随后非法流转不产生新事件，
    用「下一次合法流转收到的是本次的 ticket.update」证明非法流转未推送。
    """
    from app.auth.security import create_access_token

    customer = _create_customer(db, phone="13900000062")
    token = create_access_token(customer.id)
    ticket = _create_ticket(db, customer)
    headers = {"Authorization": f"Bearer {token}"}

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.message

        # 合法流转：processing（消费本次 ticket.update）
        resp = ws_client.patch(
            f"/tickets/{ticket.id}", json={"status": "processing"}, headers=headers
        )
        assert resp.status_code == 200
        event = ws.receive_json()
        assert event["event"] == "ticket.update"
        assert event["data"]["status"] == "processing"

        # 非法流转：办理类不支持 dispatched（仅工单类状态）
        resp = ws_client.patch(
            f"/tickets/{ticket.id}",
            json={"status": "dispatched"},
            headers=headers,
        )
        assert resp.status_code == 422

        # 再合法流转 effective：收到的是本次的 ticket.update（说明非法流转确实无推送）
        resp = ws_client.patch(
            f"/tickets/{ticket.id}", json={"status": "effective"}, headers=headers
        )
        assert resp.status_code == 200
        event = ws.receive_json()
        assert event["event"] == "ticket.update"
        assert event["data"]["old_status"] == "processing"
        assert event["data"]["status"] == "effective"


def test_ws_notification_push_on_transaction_effective(ws_client, db):
    """办理类流转至 effective：先 ticket.update，后 notification.push。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db, phone="13900000063")
    token = create_access_token(customer.id)
    ticket = _create_ticket(db, customer)
    headers = {"Authorization": f"Bearer {token}"}

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.message

        # pending → processing：仅 ticket.update
        resp = ws_client.patch(
            f"/tickets/{ticket.id}", json={"status": "processing"}, headers=headers
        )
        assert resp.status_code == 200
        event = ws.receive_json()
        assert event["event"] == "ticket.update"

        # processing → effective：ticket.update + notification.push
        resp = ws_client.patch(
            f"/tickets/{ticket.id}", json={"status": "effective"}, headers=headers
        )
        assert resp.status_code == 200
        events = [ws.receive_json(), ws.receive_json()]
        names = [e["event"] for e in events]

    assert names == ["ticket.update", "notification.push"]
    note = next(e["data"] for e in events if e["event"] == "notification.push")
    assert note["ticket_id"] == ticket.id
    assert note["message"] == "您的办理工单已生效"
    assert isinstance(note["id"], int)
    assert isinstance(note["created_at"], str)


def test_ws_notification_push_on_ticketing_dispatched(ws_client, db):
    """工单类流转至 dispatched：推送 notification.push（派单通知）。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db, phone="13900000064")
    token = create_access_token(customer.id)
    ticket = _create_ticket(db, customer, ticket_type="ticketing")
    headers = {"Authorization": f"Bearer {token}"}

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.message
        resp = ws_client.patch(
            f"/tickets/{ticket.id}", json={"status": "dispatched"}, headers=headers
        )
        assert resp.status_code == 200
        events = [ws.receive_json(), ws.receive_json()]

    names = [e["event"] for e in events]
    assert names == ["ticket.update", "notification.push"]
    note = next(e["data"] for e in events if e["event"] == "notification.push")
    assert note["message"] == "您的工单已派单"


async def test_notification_persisted_on_effective(db_client, db):
    """办理类生效时，站内通知持久化到 notifications 表（UI-C-4 通知预览条数据源）。"""
    from sqlalchemy import select

    from app.models import Notification, Ticket

    customer, token = await _login(db_client, db, phone="13900000065")
    conv = await _create_conversation(db, customer_id=customer.id)
    ticket = Ticket(
        conversation_id=conv.id,
        ticket_type="transaction",
        status="pending",
        content="套餐变更",
        customer_id=customer.id,
        creator_type="customer",
        creator_id=customer.id,
    )
    db.add(ticket)
    db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    resp = await db_client.patch(
        f"/tickets/{ticket.id}", json={"status": "processing"}, headers=headers
    )
    assert resp.status_code == 200
    resp = await db_client.patch(
        f"/tickets/{ticket.id}", json={"status": "effective"}, headers=headers
    )
    assert resp.status_code == 200

    notes = list(db.execute(select(Notification)).scalars())
    assert len(notes) == 1
    assert notes[0].ticket_id == ticket.id
    assert notes[0].customer_id == customer.id
    assert notes[0].message == "您的办理工单已生效"
    assert notes[0].read is False


async def _login(db_client, db, phone: str = "13900000040", password: str = "svc12345"):
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


async def _create_conversation(db, customer_id: int | None = None, status: str = "authenticated"):
    from app.models import Conversation

    conv = Conversation(customer_id=customer_id, status=status)
    db.add(conv)
    db.commit()
    return conv
