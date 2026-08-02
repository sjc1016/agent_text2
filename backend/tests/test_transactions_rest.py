"""B6 循环4-5：/transactions/* REST + WS 推送 + 执行复核闭环（HTTP/WS 集成 seam）。

验收标准（issue #14）：
  - 办理类 tool/REST 发起后推送 second.confirm 含结构化业务影响，会话进入 In-Progress
  - 用户确认后创建 Ticket（Pending）入队，会话回退 Authenticated，未确认不入队
  - 办理类不直接生效，一律经 Ticket
  - Ticket 执行前推送 reauth.required，服务密码复核（/auth/reauth）通过后
    Processing→执行→Effective/Failed
  - 四类办理（套餐变更/增值订退/停机保号/充值缴费）均可发起

PRD 依据：
  - 实现决策 › API 契约（/transactions/*）/ 办理流程
  - 测试决策 › HTTP 集成 seam / WS 事件 seam / 调度任务 seam
  - 用户故事 US-8~US-12
"""

from typing import Any

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


async def _login(db_client, db, phone: str = "13900000300", password: str = "svc12345"):
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


async def _reauth(db_client, token: str, password: str = "svc12345"):
    """服务密码复核 → execute_token（B1 已有端点，办理执行复核凭证）。"""
    resp = await db_client.post(
        "/auth/reauth",
        json={"service_password": password},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    return resp.json()["execute_token"]


async def _create_conversation(db, customer_id: int | None = None, status: str = "authenticated"):
    from app.models import Conversation

    conv = Conversation(customer_id=customer_id, status=status)
    db.add(conv)
    db.commit()
    return conv


def _seed_account(db, customer_id: int):
    from datetime import date

    from app.models.inquiry import CustomerAccount

    db.add(
        CustomerAccount(
            customer_id=customer_id,
            balance=50.0,
            plan_name="畅享5G套餐",
            plan_price=99.0,
            contract_expiry_date=date(2027, 6, 30),
        )
    )
    db.commit()


def _seed_plan(db, name: str = "畅享99套餐", price: float = 99.0):
    from app.models.general import Plan

    db.add(Plan(name=name, price=price, data_allowance="30GB", call_minutes="1000分钟"))
    db.commit()


def _create_pending_transaction_ticket(db, customer, content: str = "充值缴费 100 元"):
    from app.models import Conversation, Ticket
    from app.models.ticket import TicketStatus, TicketType

    conv = Conversation(customer_id=customer.id, status="authenticated")
    db.add(conv)
    db.commit()
    ticket = Ticket(
        conversation_id=conv.id,
        ticket_type=TicketType.TRANSACTION,
        status=TicketStatus.PENDING,
        content=content,
        customer_id=customer.id,
        creator_type="customer",
        creator_id=customer.id,
    )
    db.add(ticket)
    db.commit()
    return ticket


# ---------------------------------------------------------------------------
# 发起（验收1 + 验收5）：四类办理均可发起，返回结构化影响，会话进入 In-Progress
# ---------------------------------------------------------------------------


async def test_initiate_plan_change_returns_business_impact(db_client, db):
    """发起套餐变更 → 返回结构化业务影响（四要素），会话进入 in_progress。"""
    customer, token = await _login(db_client, db, phone="13900000301")
    conv = await _create_conversation(db, customer_id=customer.id)
    _seed_account(db, customer.id)
    _seed_plan(db)

    resp = await db_client.post(
        "/transactions/plan-change",
        json={"conversation_id": conv.id, "target_plan": "畅享99套餐"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["transaction_type"] == "plan_change"
    impact = body["business_impact"]
    for key in ["summary", "plan_comparison", "effective_time", "contract_impact", "fee_change"]:
        assert impact[key]
    assert "畅享99套餐" in impact["plan_comparison"]
    db.refresh(conv)
    assert conv.status == "in_progress"


async def test_initiate_all_four_transaction_types(db_client, db):
    """四类办理均可发起（验收5）。"""
    customer, token = await _login(db_client, db, phone="13900000302")
    _seed_plan(db)
    headers = {"Authorization": f"Bearer {token}"}

    cases: list[tuple[str, dict[str, Any]]] = [
        ("/transactions/plan-change", {"target_plan": "畅享99套餐"}),
        ("/transactions/vadd-change", {"service_name": "彩铃", "action": "cancel"}),
        ("/transactions/suspend-hold", {}),
        ("/transactions/recharge", {"amount": 100}),
    ]
    for path, extra in cases:
        # 每类办理使用新会话（发起后会话进入 in_progress，不可在同一会话连续发起）
        conv = await _create_conversation(db, customer_id=customer.id)
        payload: dict[str, Any] = {"conversation_id": conv.id, **extra}
        resp = await db_client.post(path, json=payload, headers=headers)
        assert resp.status_code == 200, f"{path}: {resp.text}"
        assert resp.json()["business_impact"]["summary"]


async def test_initiate_unauthenticated_returns_401(db_client, db):
    """发起未认证 → 401。"""
    conv = await _create_conversation(db, customer_id=None, status="unauthenticated")
    resp = await db_client.post(
        "/transactions/recharge",
        json={"conversation_id": conv.id, "amount": 100},
    )
    assert resp.status_code == 401


async def test_initiate_other_customer_conversation_returns_404(db_client, db):
    """发起他人会话 → 404（不泄露存在性）。"""
    from app.models import Customer

    customer, token = await _login(db_client, db, phone="13900000303")
    other = Customer(phone="13900000350", service_password_hash=_hash_password("svc12345"))
    db.add(other)
    db.commit()
    other_conv = await _create_conversation(db, customer_id=other.id)

    resp = await db_client.post(
        "/transactions/recharge",
        json={"conversation_id": other_conv.id, "amount": 100},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_initiate_on_unauthenticated_conversation_returns_422(db_client, db):
    """会话未认证（unauthenticated）→ 发起 422，状态不变更。"""
    customer, token = await _login(db_client, db, phone="13900000304")
    conv = await _create_conversation(db, customer_id=customer.id, status="unauthenticated")

    resp = await db_client.post(
        "/transactions/recharge",
        json={"conversation_id": conv.id, "amount": 100},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 422
    db.refresh(conv)
    assert conv.status == "unauthenticated"


async def test_initiate_plan_change_unknown_plan_returns_422(db_client, db):
    """目标套餐不存在 → 422（诚实拒绝，不编造）。"""
    customer, token = await _login(db_client, db, phone="13900000305")
    conv = await _create_conversation(db, customer_id=customer.id)
    _seed_account(db, customer.id)

    resp = await db_client.post(
        "/transactions/plan-change",
        json={"conversation_id": conv.id, "target_plan": "不存在的套餐"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 确认（验收2+3）：确认后创建 Ticket(Pending) 入队，会话回退 Authenticated
# ---------------------------------------------------------------------------


async def test_confirm_creates_ticket_and_conversation_back(db_client, db):
    """发起后确认 → 201 创建办理类 Ticket(Pending)，会话回退 authenticated。"""
    customer, token = await _login(db_client, db, phone="13900000306")
    conv = await _create_conversation(db, customer_id=customer.id)
    headers = {"Authorization": f"Bearer {token}"}
    await db_client.post(
        "/transactions/recharge",
        json={"conversation_id": conv.id, "amount": 100},
        headers=headers,
    )

    resp = await db_client.post(
        "/transactions/confirm",
        json={"conversation_id": conv.id, "content": "充值缴费 100 元"},
        headers=headers,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["ticket_type"] == "transaction"
    assert body["status"] == "pending"
    assert body["customer_id"] == customer.id
    assert body["content"] == "充值缴费 100 元"
    db.refresh(conv)
    assert conv.status == "authenticated"


async def test_confirm_without_initiate_returns_422(db_client, db):
    """未发起（会话仍 authenticated）直接确认 → 422。"""
    customer, token = await _login(db_client, db, phone="13900000307")
    conv = await _create_conversation(db, customer_id=customer.id)

    resp = await db_client.post(
        "/transactions/confirm",
        json={"conversation_id": conv.id, "content": "充值缴费"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 422


async def test_no_ticket_created_without_confirmation(db_client, db):
    """发起后未确认 → 无 Ticket 入队（未确认不入队）。"""
    from sqlalchemy import select

    from app.models import Ticket

    customer, token = await _login(db_client, db, phone="13900000308")
    conv = await _create_conversation(db, customer_id=customer.id)
    headers = {"Authorization": f"Bearer {token}"}
    await db_client.post(
        "/transactions/suspend-hold",
        json={"conversation_id": conv.id},
        headers=headers,
    )

    tickets = list(db.execute(select(Ticket)).scalars())
    assert tickets == []


# ---------------------------------------------------------------------------
# 执行复核（验收4）：reauth → execute_token → Processing → 执行 → Effective
# ---------------------------------------------------------------------------


async def test_execute_with_access_token_returns_401(db_client, db):
    """access token（未复核）调执行端点 → 401（必须 execute_token）。"""
    customer, token = await _login(db_client, db, phone="13900000309")
    ticket = _create_pending_transaction_ticket(db, customer)

    resp = await db_client.post(
        f"/transactions/{ticket.id}/execute",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 401
    db.refresh(ticket)
    assert ticket.status.value == "pending"  # 未执行


async def test_execute_without_token_returns_401(db_client, db):
    """无 token 调执行端点 → 401。"""
    customer, _ = await _login(db_client, db, phone="13900000310")
    ticket = _create_pending_transaction_ticket(db, customer)

    resp = await db_client.post(f"/transactions/{ticket.id}/execute")
    assert resp.status_code == 401


async def test_execute_after_reauth_reaches_effective(db_client, db):
    """/auth/reauth 复核 → execute_token 执行 → 200，Ticket 变 effective。"""
    customer, token = await _login(db_client, db, phone="13900000311")
    ticket = _create_pending_transaction_ticket(db, customer)
    execute_token = await _reauth(db_client, token)

    resp = await db_client.post(
        f"/transactions/{ticket.id}/execute",
        headers={"Authorization": f"Bearer {execute_token}"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "effective"
    assert body["id"] == ticket.id


async def test_execute_other_customer_ticket_returns_404(db_client, db):
    """execute_token 复核他人 Ticket → 404。"""
    from app.models import Customer

    owner = Customer(phone="13900000351", service_password_hash=_hash_password("svc12345"))
    db.add(owner)
    db.commit()
    ticket = _create_pending_transaction_ticket(db, owner)
    customer, token = await _login(db_client, db, phone="13900000312")
    execute_token = await _reauth(db_client, token)

    resp = await db_client.post(
        f"/transactions/{ticket.id}/execute",
        headers={"Authorization": f"Bearer {execute_token}"},
    )

    assert resp.status_code == 404


async def test_execute_non_pending_returns_422(db_client, db):
    """终态（effective）Ticket 执行 → 422。"""
    from app.models.ticket import TicketStatus

    customer, token = await _login(db_client, db, phone="13900000313")
    ticket = _create_pending_transaction_ticket(db, customer)
    ticket.status = TicketStatus.EFFECTIVE
    db.commit()
    execute_token = await _reauth(db_client, token)

    resp = await db_client.post(
        f"/transactions/{ticket.id}/execute",
        headers={"Authorization": f"Bearer {execute_token}"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# WS 推送（验收1+4）：second.confirm / conversation.state / reauth.required / ticket.update
# ---------------------------------------------------------------------------


def test_ws_second_confirm_on_initiate(ws_client, db):
    """发起办理 → 客户连接收到 second.confirm（含结构化影响）+ conversation.state(in_progress)。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db, phone="13900000320")
    conv = _create_conversation_sync(db, customer)
    _seed_plan(db)
    token = create_access_token(customer.id)

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.message（accept）
        resp = ws_client.post(
            "/transactions/plan-change",
            json={"conversation_id": conv.id, "target_plan": "畅享99套餐"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        events = [ws.receive_json(), ws.receive_json()]

    names = [e["event"] for e in events]
    assert names == ["second.confirm", "conversation.state"]
    confirm = next(e["data"] for e in events if e["event"] == "second.confirm")
    assert confirm["conversation_id"] == conv.id
    assert confirm["transaction_type"] == "plan_change"
    impact = confirm["business_impact"]
    for key in ["summary", "plan_comparison", "effective_time", "contract_impact", "fee_change"]:
        assert impact[key]
    state = next(e["data"] for e in events if e["event"] == "conversation.state")
    assert state["old_state"] == "authenticated"
    assert state["new_state"] == "in_progress"


def test_ws_conversation_state_back_on_confirm(ws_client, db):
    """确认入队 → 客户连接收到 conversation.state（in_progress → authenticated）。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db, phone="13900000321")
    conv = _create_conversation_sync(db, customer)
    token = create_access_token(customer.id)

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.message
        resp = ws_client.post(
            "/transactions/recharge",
            json={"conversation_id": conv.id, "amount": 100},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        ws.receive_json()  # second.confirm
        state = ws.receive_json()
        assert state["event"] == "conversation.state"
        assert state["data"]["new_state"] == "in_progress"

        resp = ws_client.post(
            "/transactions/confirm",
            json={"conversation_id": conv.id, "content": "充值缴费 100 元"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        state = ws.receive_json()

    assert state["event"] == "conversation.state"
    assert state["data"]["old_state"] == "in_progress"
    assert state["data"]["new_state"] == "authenticated"


def test_ws_reauth_required_on_execution_trigger(ws_client, db):
    """调度 seam（POST /transactions/{id}/reauth）→ 客户收到 reauth.required。

    模拟调度任务：扫描待执行办理类 Ticket，触发执行前服务密码复核（US-12）。
    """
    from app.auth.security import create_access_token

    customer = _create_customer(db, phone="13900000322")
    ticket = _create_ticket_sync(db, customer)
    token = create_access_token(customer.id)

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.message
        # 调度任务 seam：执行前触发复核（REST 暴露，ASGI 上下文内推送 reauth.required）
        resp = ws_client.post(
            f"/transactions/{ticket.id}/reauth",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        event = ws.receive_json()

    assert event["event"] == "reauth.required"
    payload = event["data"]
    assert payload["ticket_id"] == ticket.id
    assert payload["conversation_id"] == ticket.conversation_id
    assert isinstance(payload["message"], str)
    assert isinstance(payload["requested_at"], str)


def test_ws_ticket_update_and_notification_on_execute(ws_client, db):
    """执行生效 → 客户收到 ticket.update + notification.push（生效通知）。"""
    from app.auth.security import create_access_token, create_execute_token

    customer = _create_customer(db, phone="13900000323")
    ticket = _create_ticket_sync(db, customer)
    token = create_access_token(customer.id)
    execute_token = create_execute_token(customer.id)

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.message
        resp = ws_client.post(
            f"/transactions/{ticket.id}/execute",
            headers={"Authorization": f"Bearer {execute_token}"},
        )
        assert resp.status_code == 200
        events = [ws.receive_json(), ws.receive_json()]

    names = [e["event"] for e in events]
    assert names == ["ticket.update", "notification.push"]
    note = next(e["data"] for e in events if e["event"] == "notification.push")
    assert note["ticket_id"] == ticket.id
    assert note["message"] == "您的办理工单已生效"


# ---------------------------------------------------------------------------
# 审计留痕（CONTEXT › 审计日志：办理类发起/二次确认/入队/执行）
# ---------------------------------------------------------------------------


async def test_audit_log_records_transaction_lifecycle(db_client, db):
    """发起/确认/执行全流程写审计（transaction.initiate/confirm/execute）。"""
    from sqlalchemy import select

    from app.models import AuditLog

    customer, token = await _login(db_client, db, phone="13900000330")
    conv = await _create_conversation(db, customer_id=customer.id)
    headers = {"Authorization": f"Bearer {token}"}

    await db_client.post(
        "/transactions/suspend-hold", json={"conversation_id": conv.id}, headers=headers
    )
    await db_client.post(
        "/transactions/confirm",
        json={"conversation_id": conv.id, "content": "停机保号"},
        headers=headers,
    )
    ticket = _create_pending_transaction_ticket(db, customer)
    execute_token = await _reauth(db_client, token)
    await db_client.post(
        f"/transactions/{ticket.id}/execute",
        headers={"Authorization": f"Bearer {execute_token}"},
    )

    actions = [row.action for row in db.execute(select(AuditLog).order_by(AuditLog.id)).scalars()]
    assert "transaction.initiate" in actions
    assert "transaction.confirm" in actions
    assert "transaction.execute" in actions


# --- 同步 helper（ws_client 场景） ---


def _create_customer(db, phone: str = "13900000320", password: str = "svc12345"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password(password))
    db.add(customer)
    db.commit()
    return customer


def _create_conversation_sync(db, customer):
    from app.models import Conversation

    conv = Conversation(customer_id=customer.id, status="authenticated")
    db.add(conv)
    db.commit()
    return conv


def _create_ticket_sync(db, customer, content: str = "充值缴费 100 元"):
    from app.models import Ticket
    from app.models.ticket import TicketStatus, TicketType

    conv = _create_conversation_sync(db, customer)
    ticket = Ticket(
        conversation_id=conv.id,
        ticket_type=TicketType.TRANSACTION,
        status=TicketStatus.PENDING,
        content=content,
        customer_id=customer.id,
        creator_type="customer",
        creator_id=customer.id,
    )
    db.add(ticket)
    db.commit()
    return ticket
