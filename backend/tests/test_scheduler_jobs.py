"""B10 调度任务 seam 测试（issue #19）。

PRD 依据：测试决策 › 调度任务 seam —— 直接调用 APScheduler job 函数（不启
调度器），验证状态机流转与副作用。

覆盖验收标准（issue #19）：
  1. Ticket 待执行→执行中触发服务密码复核 job（US-12）
  2. 会话超时检测断开 Session 并开启新 Session 归属同一 Conversation（US-18）
  3. 坐席状态监控 job 正确运行
  4. 离线兜底回呼 Ticket 派单 job 派单到 Skill Group（US-29）
"""

from datetime import datetime

import bcrypt
from sqlalchemy import select

from app.scheduler.jobs import (
    close_timed_out_sessions,
    dispatch_callback_tickets,
    ensure_active_session,
    monitor_agent_availability,
    trigger_pending_transaction_reauth,
)

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_customer(db, phone: str = "13800000111"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password("x"))
    db.add(customer)
    db.commit()
    return customer


def _create_agent(db, employee_id: str = "A6001", status: str = "online"):
    from app.models import User

    agent = User(
        employee_id=employee_id,
        password_hash=_hash_password("agent-pass"),
        name="坐席六",
        status=status,
    )
    db.add(agent)
    db.commit()
    return agent


def _create_conversation(db, customer_id: int | None = None, status: str = "authenticated"):
    from app.models import Conversation

    conv = Conversation(customer_id=customer_id, status=status)
    db.add(conv)
    db.commit()
    return conv


def _create_ticket(
    db,
    conversation_id: int,
    *,
    ticket_type: str = "ticketing",
    content: str = "",
    status: str = "pending",
    skill_group: str | None = None,
    customer_id: int | None = None,
):
    from app.models import Ticket
    from app.models.ticket import TicketStatus, TicketType

    ticket = Ticket(
        conversation_id=conversation_id,
        ticket_type=TicketType(ticket_type),
        status=TicketStatus(status),
        content=content,
        skill_group=skill_group,
        customer_id=customer_id,
        creator_type="assistant",
    )
    db.add(ticket)
    db.commit()
    return ticket


class TestDispatchCallbackTickets:
    """验收4：离线兜底回呼 Ticket 派单 job（US-29）。

    CONTEXT › 离线兜底：回呼请求 Ticket 派单到对应 Skill Group。job 为补漏兜底——
    确保 content 以 [回呼请求] 开头的工单类 Ticket 均已派单（pending → dispatched）。
    """

    async def test_dispatches_pending_callback_ticket_to_skill_group(self, db):
        from app.handoff.service import CALLBACK_TICKET_CONTENT_PREFIX

        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)
        ticket = _create_ticket(
            db,
            conv.id,
            content=f"{CALLBACK_TICKET_CONTENT_PREFIX} 转接原因：explicit_request",
            status="pending",
            skill_group="投诉处理组",
            customer_id=customer.id,
        )

        dispatched = await dispatch_callback_tickets(db)

        assert dispatched == 1
        db.refresh(ticket)
        assert ticket.status.value == "dispatched"
        assert ticket.skill_group == "投诉处理组"

    async def test_skips_already_dispatched_callback_ticket(self, db):
        from app.handoff.service import CALLBACK_TICKET_CONTENT_PREFIX

        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)
        ticket = _create_ticket(
            db,
            conv.id,
            content=f"{CALLBACK_TICKET_CONTENT_PREFIX} 转接原因：compliance_risk",
            status="dispatched",
            skill_group="套餐业务组",
            customer_id=customer.id,
        )

        dispatched = await dispatch_callback_tickets(db)

        assert dispatched == 0
        db.refresh(ticket)
        assert ticket.status.value == "dispatched"

    async def test_skips_non_callback_pending_ticket(self, db):
        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)
        ticket = _create_ticket(
            db,
            conv.id,
            content="家里宽带故障，请求维修",
            status="pending",
            customer_id=customer.id,
        )

        dispatched = await dispatch_callback_tickets(db)

        assert dispatched == 0
        db.refresh(ticket)
        assert ticket.status.value == "pending"


class TestCloseTimedOutSessions:
    """验收2（前半）：会话超时检测 job（US-18）。

    CONTEXT › 会话片段：Session 一段连续活跃交互，超时后断开（ended_at 落位）。
    """

    async def test_closes_sessions_idle_past_timeout(self, db):
        from app.models import Session

        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)
        active = Session(conversation_id=conv.id, started_at=datetime(2026, 1, 1, 8, 0))
        db.add(active)
        db.commit()

        now = datetime(2026, 1, 1, 9, 0)
        closed = await close_timed_out_sessions(db, now=now, timeout_minutes=30)

        assert closed == 1
        db.refresh(active)
        assert active.ended_at == now

    async def test_keeps_fresh_active_session_open(self, db):
        from app.models import Session

        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)
        active = Session(conversation_id=conv.id, started_at=datetime(2026, 1, 1, 8, 55))
        db.add(active)
        db.commit()

        closed = await close_timed_out_sessions(
            db, now=datetime(2026, 1, 1, 9, 0), timeout_minutes=30
        )

        assert closed == 0
        db.refresh(active)
        assert active.ended_at is None

    async def test_skips_already_ended_sessions(self, db):
        from app.models import Session

        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)
        ended = Session(
            conversation_id=conv.id,
            started_at=datetime(2026, 1, 1, 8, 0),
            ended_at=datetime(2026, 1, 1, 8, 40),
        )
        db.add(ended)
        db.commit()

        closed = await close_timed_out_sessions(
            db, now=datetime(2026, 1, 1, 9, 0), timeout_minutes=30
        )

        assert closed == 0
        db.refresh(ended)
        assert ended.ended_at == datetime(2026, 1, 1, 8, 40)


class TestEnsureActiveSession:
    """验收2（后半）：超时后重新交互开启新 Session，归属同一 Conversation（US-18）。"""

    async def test_opens_new_session_when_existing_is_timed_out(self, db):
        from app.models import Session

        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)
        old = Session(conversation_id=conv.id, started_at=datetime(2026, 1, 1, 8, 0))
        db.add(old)
        db.commit()

        now = datetime(2026, 1, 1, 9, 0)
        current = await ensure_active_session(db, conv, now=now, timeout_minutes=30)

        assert current.id != old.id
        assert current.conversation_id == conv.id
        db.refresh(old)
        assert old.ended_at == now

    async def test_returns_existing_session_when_fresh(self, db):
        from app.models import Session

        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)
        active = Session(conversation_id=conv.id, started_at=datetime(2026, 1, 1, 8, 55))
        db.add(active)
        db.commit()

        current = await ensure_active_session(
            db, conv, now=datetime(2026, 1, 1, 9, 0), timeout_minutes=30
        )

        assert current.id == active.id
        db.refresh(active)
        assert active.ended_at is None

    async def test_creates_first_session_when_none(self, db):
        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)

        current = await ensure_active_session(
            db, conv, now=datetime(2026, 1, 1, 9, 0), timeout_minutes=30
        )

        assert current.conversation_id == conv.id
        assert current.ended_at is None


class TestMonitorAgentAvailability:
    """验收3：坐席状态监控 job。

    CONTEXT › 离线兜底：无在线坐席（全忙超阈值）时进入离线兜底。
    job 统计在线坐席，全忙时写审计告警留痕。
    """

    async def test_writes_alert_audit_when_all_agents_busy(self, db):
        from app.models import AuditLog

        _create_agent(db, status="offline")

        result = await monitor_agent_availability(db)

        assert result == {"online_agents": 0, "all_busy": True}
        db.expire_all()
        logs = (
            db.execute(select(AuditLog).where(AuditLog.action == "agent.availability.alert"))
            .scalars()
            .all()
        )
        assert len(logs) == 1
        assert logs[0].detail["online_agents"] == 0

    async def test_no_alert_when_online_agents_exist(self, db):
        from app.models import AuditLog

        _create_agent(db, status="online")

        result = await monitor_agent_availability(db)

        assert result == {"online_agents": 1, "all_busy": False}
        db.expire_all()
        logs = (
            db.execute(select(AuditLog).where(AuditLog.action == "agent.availability.alert"))
            .scalars()
            .all()
        )
        assert logs == []


class TestTriggerPendingTransactionReauth:
    """验收1：Ticket 待执行→执行中触发服务密码复核 job（US-12）。

    CONTEXT › 办理执行复核：办理类 Ticket 待执行进入执行中前必须复核服务密码。
    job 扫描待执行办理类 Ticket，校验后推送 reauth.required（WS）+ 审计留痕。
    """

    async def test_triggers_reauth_for_pending_transaction_ticket(self, db):
        from app.models import AuditLog

        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)
        ticket = _create_ticket(
            db,
            conv.id,
            ticket_type="transaction",
            content="套餐变更申请",
            status="pending",
            customer_id=customer.id,
        )

        triggered = await trigger_pending_transaction_reauth(db)

        assert triggered == 1
        db.refresh(ticket)
        assert ticket.status.value == "pending"  # 复核触发不流转状态，等待用户 /auth/reauth
        db.expire_all()
        logs = (
            db.execute(select(AuditLog).where(AuditLog.action == "transaction.reauth_request"))
            .scalars()
            .all()
        )
        assert len(logs) == 1
        assert logs[0].detail["ticket_id"] == ticket.id

    async def test_skips_non_transaction_ticket(self, db):
        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)
        ticket = _create_ticket(db, conv.id, content="宽带故障报修", status="pending")

        triggered = await trigger_pending_transaction_reauth(db)

        assert triggered == 0
        db.refresh(ticket)
        assert ticket.status.value == "pending"

    async def test_skips_transaction_ticket_without_customer(self, db):
        conv = _create_conversation(db, customer_id=None)
        ticket = _create_ticket(
            db, conv.id, ticket_type="transaction", content="套餐变更", status="pending"
        )

        triggered = await trigger_pending_transaction_reauth(db)

        assert triggered == 0
        db.refresh(ticket)
        assert ticket.status.value == "pending"
