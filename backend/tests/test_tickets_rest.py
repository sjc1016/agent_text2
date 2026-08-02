"""B7 循环1-5：工单 REST CRUD + 双状态机 + 一会话多工单。

验收标准（issue #10）：
  POST /tickets 创建工单（办理类/工单类），Visitor 创建时 customer 允许 null 仅记录联系方式
  办理类状态机流转 Pending→Processing→Effective/Failed/Cancelled，非法流转拒绝
  工单类状态机流转 Pending→Dispatched→In-Progress→Awaiting-confirmation→Closed/Cancelled
  一个 Conversation 可并存多个 Ticket
  （PRD 依据：实现决策 › 工单状态机 + API 契约 / RESTful 端点；
              测试决策 › HTTP 集成 seam；用户故事 US-13, US-14, US-23, US-24）

鉴权复用 B1 的 Authorization header Bearer（CurrentCustomer）。
"""

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


async def _login(db_client, db, phone: str = "13900000040", password: str = "svc12345"):
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


async def _create_conversation(db, customer_id: int | None = None, status: str = "authenticated"):
    from app.models import Conversation

    conv = Conversation(customer_id=customer_id, status=status)
    db.add(conv)
    db.commit()
    return conv


async def test_create_ticket_unauthenticated_returns_401(db_client, db):
    conv = await _create_conversation(db, customer_id=None, status="unauthenticated")

    response = await db_client.post(
        "/tickets",
        json={
            "conversation_id": conv.id,
            "ticket_type": "transaction",
            "content": "将套餐变更为 99 元档",
        },
    )
    assert response.status_code == 401


async def test_create_transaction_ticket_returns_201_with_pending_status(db_client, db):
    """认证客户创建办理类工单 → 201，默认状态 pending（待执行）。"""
    customer, token = await _login(db_client, db, phone="13900000041")
    conv = await _create_conversation(db, customer_id=customer.id)

    response = await db_client.post(
        "/tickets",
        json={
            "conversation_id": conv.id,
            "ticket_type": "transaction",
            "content": "将套餐变更为 99 元档",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["ticket_type"] == "transaction"
    assert body["status"] == "pending"
    assert body["conversation_id"] == conv.id
    assert body["customer_id"] == customer.id
    assert body["content"] == "将套餐变更为 99 元档"
    assert isinstance(body["id"], int)
    assert isinstance(body["created_at"], str)


async def test_create_ticketing_ticket_returns_201_with_pending_status(db_client, db):
    """认证客户创建工单类（故障报修）工单 → 201，默认 pending（待派单）。"""
    customer, token = await _login(db_client, db, phone="13900000042")
    conv = await _create_conversation(db, customer_id=customer.id)

    response = await db_client.post(
        "/tickets",
        json={
            "conversation_id": conv.id,
            "ticket_type": "ticketing",
            "content": "宽带无法连接，请上门维修",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["ticket_type"] == "ticketing"
    assert body["status"] == "pending"


async def test_create_ticket_rejects_unknown_type(db_client, db):
    """未知工单类型 → 422（ticket_type 仅 transaction/ticketing 两类）。"""
    customer, token = await _login(db_client, db, phone="13900000043")
    conv = await _create_conversation(db, customer_id=customer.id)

    response = await db_client.post(
        "/tickets",
        json={"conversation_id": conv.id, "ticket_type": "refund", "content": "未知类型"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


async def test_list_tickets_unauthenticated_returns_401(db_client, db):
    response = await db_client.get("/tickets")
    assert response.status_code == 401


async def test_list_tickets_returns_only_own(db_client, db):
    """GET /tickets 仅返回当前客户的工单（他人工单不可见）。"""
    from app.models import Customer, Ticket

    customer, token = await _login(db_client, db, phone="13900000044")
    conv = await _create_conversation(db, customer_id=customer.id)
    db.add(
        Ticket(
            conversation_id=conv.id,
            ticket_type="transaction",
            status="pending",
            content="本人工单",
            customer_id=customer.id,
            creator_type="customer",
            creator_id=customer.id,
        )
    )
    # 他人客户（真实存在，满足 FK 约束）
    other_customer = Customer(phone="13900000055", service_password_hash=_hash_password("svc12345"))
    db.add(other_customer)
    db.commit()
    # 他人工单
    db.add(
        Ticket(
            conversation_id=conv.id,
            ticket_type="ticketing",
            status="pending",
            content="他人工单",
            customer_id=other_customer.id,
            creator_type="customer",
            creator_id=other_customer.id,
        )
    )
    db.commit()

    response = await db_client.get("/tickets", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["content"] == "本人工单"
    assert items[0]["customer_id"] == customer.id


async def test_get_ticket_detail_returns_own_ticket(db_client, db):
    """GET /tickets/{id} 返回本人工单详情。"""
    from app.models import Ticket

    customer, token = await _login(db_client, db, phone="13900000045")
    conv = await _create_conversation(db, customer_id=customer.id)
    ticket = Ticket(
        conversation_id=conv.id,
        ticket_type="transaction",
        status="pending",
        content="详情测试",
        customer_id=customer.id,
        creator_type="customer",
        creator_id=customer.id,
    )
    db.add(ticket)
    db.commit()

    response = await db_client.get(
        f"/tickets/{ticket.id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == ticket.id
    assert body["content"] == "详情测试"
    assert body["status"] == "pending"


async def test_get_ticket_detail_other_customer_returns_404(db_client, db):
    """GET /tickets/{id} 他人工单 → 404（不泄露存在性，与会话边界一致）。"""
    from app.models import Customer, Ticket

    customer, token = await _login(db_client, db, phone="13900000046")
    conv = await _create_conversation(db, customer_id=customer.id)
    # 他人客户（真实存在，满足 FK 约束）
    other_customer = Customer(phone="13900000056", service_password_hash=_hash_password("svc12345"))
    db.add(other_customer)
    db.commit()
    other = Ticket(
        conversation_id=conv.id,
        ticket_type="transaction",
        status="pending",
        content="他人详情",
        customer_id=other_customer.id,
        creator_type="customer",
        creator_id=other_customer.id,
    )
    db.add(other)
    db.commit()

    response = await db_client.get(
        f"/tickets/{other.id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


# --- 双状态机（验收标准 2/3：非法流转拒绝） ---


async def test_transaction_state_machine_valid_flow(db_client, db):
    """办理类：pending → processing → effective 全链合法。"""
    from app.models import Ticket

    customer, token = await _login(db_client, db, phone="13900000047")
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
    assert resp.json()["status"] == "processing"

    resp = await db_client.patch(
        f"/tickets/{ticket.id}", json={"status": "effective"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "effective"


async def test_transaction_state_machine_rejects_illegal_flow(db_client, db):
    """办理类非法流转：pending → effective 直接跳转 → 422，状态不变。"""
    from app.models import Ticket

    customer, token = await _login(db_client, db, phone="13900000048")
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

    response = await db_client.patch(
        f"/tickets/{ticket.id}",
        json={"status": "effective"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    db.refresh(ticket)
    assert ticket.status == "pending"


async def test_transaction_state_machine_failed_and_cancelled(db_client, db):
    """办理类：processing → failed 合法；pending → cancelled 合法。"""
    from app.models import Ticket

    customer, token = await _login(db_client, db, phone="13900000049")
    conv = await _create_conversation(db, customer_id=customer.id)

    fail_ticket = Ticket(
        conversation_id=conv.id,
        ticket_type="transaction",
        status="pending",
        content="充值缴费",
        customer_id=customer.id,
        creator_type="customer",
        creator_id=customer.id,
    )
    cancel_ticket = Ticket(
        conversation_id=conv.id,
        ticket_type="transaction",
        status="pending",
        content="停机保号",
        customer_id=customer.id,
        creator_type="customer",
        creator_id=customer.id,
    )
    db.add_all([fail_ticket, cancel_ticket])
    db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    resp = await db_client.patch(
        f"/tickets/{fail_ticket.id}", json={"status": "processing"}, headers=headers
    )
    assert resp.status_code == 200
    resp = await db_client.patch(
        f"/tickets/{fail_ticket.id}", json={"status": "failed"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"

    resp = await db_client.patch(
        f"/tickets/{cancel_ticket.id}", json={"status": "cancelled"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


async def test_ticketing_state_machine_valid_flow(db_client, db):
    """工单类：pending → dispatched → in_progress → awaiting_confirmation → closed 全链合法。"""
    from app.models import Ticket

    customer, token = await _login(db_client, db, phone="13900000050")
    conv = await _create_conversation(db, customer_id=customer.id)
    ticket = Ticket(
        conversation_id=conv.id,
        ticket_type="ticketing",
        status="pending",
        content="宽带故障",
        customer_id=customer.id,
        creator_type="customer",
        creator_id=customer.id,
    )
    db.add(ticket)
    db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    flow = ["dispatched", "in_progress", "awaiting_confirmation", "closed"]
    for state in flow:
        resp = await db_client.patch(
            f"/tickets/{ticket.id}", json={"status": state}, headers=headers
        )
        assert resp.status_code == 200, f"跳转 {state} 失败: {resp.text}"
        assert resp.json()["status"] == state


async def test_ticketing_state_machine_rejects_illegal_flow(db_client, db):
    """工单类非法流转：pending → in_progress 直接跳转 → 422。"""
    from app.models import Ticket

    customer, token = await _login(db_client, db, phone="13900000051")
    conv = await _create_conversation(db, customer_id=customer.id)
    ticket = Ticket(
        conversation_id=conv.id,
        ticket_type="ticketing",
        status="pending",
        content="宽带故障",
        customer_id=customer.id,
        creator_type="customer",
        creator_id=customer.id,
    )
    db.add(ticket)
    db.commit()

    response = await db_client.patch(
        f"/tickets/{ticket.id}",
        json={"status": "in_progress"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    db.refresh(ticket)
    assert ticket.status == "pending"


async def test_ticketing_state_machine_cancelled_from_processing(db_client, db):
    """工单类：in_progress → cancelled 合法（处理中可取消）。"""
    from app.models import Ticket

    customer, token = await _login(db_client, db, phone="13900000052")
    conv = await _create_conversation(db, customer_id=customer.id)
    ticket = Ticket(
        conversation_id=conv.id,
        ticket_type="ticketing",
        status="pending",
        content="宽带故障",
        customer_id=customer.id,
        creator_type="customer",
        creator_id=customer.id,
    )
    db.add(ticket)
    db.commit()
    headers = {"Authorization": f"Bearer {token}"}

    for state in ["dispatched", "in_progress"]:
        resp = await db_client.patch(
            f"/tickets/{ticket.id}", json={"status": state}, headers=headers
        )
        assert resp.status_code == 200

    resp = await db_client.patch(
        f"/tickets/{ticket.id}", json={"status": "cancelled"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


async def test_terminal_state_rejects_further_transition(db_client, db):
    """终态不可再流转：effective → 任意 → 422（终端状态机守住）。"""
    from app.models import Ticket

    customer, token = await _login(db_client, db, phone="13900000053")
    conv = await _create_conversation(db, customer_id=customer.id)
    ticket = Ticket(
        conversation_id=conv.id,
        ticket_type="transaction",
        status="effective",
        content="已生效工单",
        customer_id=customer.id,
        creator_type="customer",
        creator_id=customer.id,
    )
    db.add(ticket)
    db.commit()

    response = await db_client.patch(
        f"/tickets/{ticket.id}",
        json={"status": "processing"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
    db.refresh(ticket)
    assert ticket.status == "effective"


# --- 一个 Conversation 可并存多个 Ticket（验收标准 5） ---


async def test_one_conversation_holds_multiple_tickets(db_client, db):
    """同一 Conversation 可创建多个 Ticket（办理类 + 工单类并存）。"""
    from sqlalchemy import select

    from app.models import Ticket

    customer, token = await _login(db_client, db, phone="13900000054")
    conv = await _create_conversation(db, customer_id=customer.id)
    headers = {"Authorization": f"Bearer {token}"}

    for ticket_type, content in [
        ("transaction", "套餐变更"),
        ("ticketing", "故障报修"),
        ("transaction", "充值缴费"),
    ]:
        resp = await db_client.post(
            "/tickets",
            json={"conversation_id": conv.id, "ticket_type": ticket_type, "content": content},
            headers=headers,
        )
        assert resp.status_code == 201

    tickets = list(db.execute(select(Ticket).where(Ticket.conversation_id == conv.id)).scalars())
    assert len(tickets) == 3
