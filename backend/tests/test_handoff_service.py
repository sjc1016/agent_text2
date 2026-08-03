"""B8 循环2：Handoff 执行服务（服务时间 + 全忙判定 + 触发路由：正常转接 / 离线兜底）。

验收标准（issue #17）：
  坐席服务时间 1:00-23:00，非服务时间 Handoff 进入待接入队列次日接入（US-20）
  全忙超阈值或非服务时间创建回呼请求 Ticket 派单到 Skill Group，助理不强制结束会话（US-29）

行为（CONTEXT › 服务时间与离线兜底 / 转接）：
  - 服务时间内且有在线坐席 → 正常转接：会话 → handed_off（进入待接入队列）
  - 非服务时间 或 全忙超阈值 → 离线兜底：创建回呼请求 Ticket（工单类，派单到
    Skill Group）；会话仍流转 handed_off（次日坐席接入），不置 closed（不强制结束）
  - Handoff 发起写入审计日志（CONTEXT › 审计日志：Handoff 发起与结束）
"""

from datetime import datetime

import bcrypt

from app.handoff.service import (
    AGENT_SERVICE_END_HOUR,
    AGENT_SERVICE_START_HOUR,
    all_agents_busy,
    create_callback_ticket,
    is_in_service_time,
    trigger_handoff,
)
from app.handoff.triggers import HandoffReason

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_customer(db, phone: str = "13800000111"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password("x"))
    db.add(customer)
    db.commit()
    return customer


def _create_conversation(db, customer_id: int, status: str = "authenticated"):
    from app.models import Conversation

    conv = Conversation(customer_id=customer_id, status=status)
    db.add(conv)
    db.commit()
    return conv


def _create_agent(db, status: str = "online"):
    from app.models import User

    agent = User(
        employee_id="A6001",
        password_hash=_hash_password("agent-pass"),
        name="坐席六",
        status=status,
    )
    db.add(agent)
    db.commit()
    return agent


class TestServiceTime:
    """坐席服务时间 1:00-23:00（半开区间 [1, 23)）。"""

    def test_start_hour_is_in_service_time(self):
        assert is_in_service_time(datetime(2026, 1, 1, hour=AGENT_SERVICE_START_HOUR))

    def test_minute_before_start_not_in_service_time(self):
        assert not is_in_service_time(datetime(2026, 1, 1, hour=0, minute=59))

    def test_end_hour_not_in_service_time(self):
        assert not is_in_service_time(datetime(2026, 1, 1, hour=AGENT_SERVICE_END_HOUR))

    def test_hour_before_end_in_service_time(self):
        assert is_in_service_time(datetime(2026, 1, 1, hour=AGENT_SERVICE_END_HOUR - 1))


class TestAllAgentsBusy:
    """全忙判定：无在线坐席（status=online 计数为 0）即全忙超阈值。"""

    def test_no_agents_is_busy(self, db):
        assert all_agents_busy(db)

    def test_only_offline_agents_is_busy(self, db):
        _create_agent(db, status="offline")
        assert all_agents_busy(db)

    def test_online_agent_not_busy(self, db):
        _create_agent(db, status="online")
        assert not all_agents_busy(db)


class TestTriggerHandoff:
    """触发路由：正常转接 vs 离线兜底。"""

    def test_normal_handoff_enters_queue_without_ticket(self, db):
        from app.models import Ticket

        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)
        _create_agent(db, status="online")

        outcome = trigger_handoff(
            db, conv, HandoffReason.EXPLICIT_REQUEST, now=datetime(2026, 1, 1, hour=10)
        )

        assert not outcome.offline_fallback
        assert outcome.ticket_id is None
        assert outcome.reason == HandoffReason.EXPLICIT_REQUEST
        # 会话进入待接入队列（handed_off，US-20 队列判定）
        db.refresh(conv)
        assert conv.status == "handed_off"
        # 无回呼 Ticket
        tickets = list(db.query(Ticket).all())
        assert tickets == []

    def test_offline_fallback_after_hours_creates_callback_ticket(self, db):
        from app.models import Ticket

        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)
        _create_agent(db, status="online")

        # 非服务时间（23:00）→ 离线兜底（CONTEXT › 离线兜底：非服务时间触发）
        outcome = trigger_handoff(
            db, conv, HandoffReason.EXPLICIT_REQUEST, now=datetime(2026, 1, 1, hour=23)
        )

        assert outcome.offline_fallback
        assert outcome.ticket_id is not None
        ticket = db.get(Ticket, outcome.ticket_id)
        assert ticket is not None
        # 工单类 + 派单到 Skill Group
        assert ticket.ticket_type.value == "ticketing"
        assert ticket.status.value == "dispatched"
        assert ticket.skill_group == "套餐业务组"  # 默认技能组
        assert "回呼请求" in ticket.content
        # 会话仍进入队列（不强制结束 = 不置 closed，次日坐席接入）
        db.refresh(conv)
        assert conv.status == "handed_off"

    def test_offline_fallback_all_busy_in_service_time(self, db):
        from app.models import Ticket

        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)
        _create_agent(db, status="offline")  # 服务时间内全忙 → 离线兜底

        outcome = trigger_handoff(
            db, conv, HandoffReason.COMPLIANCE_RISK, now=datetime(2026, 1, 1, hour=10)
        )

        assert outcome.offline_fallback
        assert outcome.ticket_id is not None
        ticket = db.get(Ticket, outcome.ticket_id)
        assert ticket.status.value == "dispatched"

    def test_custom_skill_group_routed(self, db):
        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)
        _create_agent(db, status="offline")

        outcome = trigger_handoff(
            db,
            conv,
            HandoffReason.NEGATIVE_SENTIMENT,
            skill_group="投诉处理组",
            now=datetime(2026, 1, 1, hour=10),
        )

        assert outcome.offline_fallback
        from app.models import Ticket

        ticket = db.get(Ticket, outcome.ticket_id)
        assert ticket.skill_group == "投诉处理组"

    def test_reason_str_accepted(self, db):
        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)
        _create_agent(db, status="online")

        outcome = trigger_handoff(db, conv, "explicit_request", now=datetime(2026, 1, 1, hour=10))

        assert outcome.reason == HandoffReason.EXPLICIT_REQUEST
        assert not outcome.offline_fallback

    def test_handoff_start_audit_written(self, db):
        from sqlalchemy import select

        from app.models import AuditLog

        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)
        _create_agent(db, status="online")

        trigger_handoff(db, conv, HandoffReason.EXPLICIT_REQUEST, now=datetime(2026, 1, 1, hour=10))

        db.expire_all()
        logs = (
            db.execute(select(AuditLog).where(AuditLog.action == "handoff.start")).scalars().all()
        )
        assert len(logs) == 1
        assert logs[0].actor_type == "assistant"
        assert logs[0].detail["conversation_id"] == conv.id
        assert logs[0].detail["reason"] == "explicit_request"


class TestCreateCallbackTicket:
    """回呼请求 Ticket：工单类 + 派单 + 技能组 + 审计。"""

    def test_callback_ticket_dispatch_and_audit(self, db):
        from sqlalchemy import select

        from app.models import AuditLog

        customer = _create_customer(db)
        conv = _create_conversation(db, customer.id)

        ticket = create_callback_ticket(db, conv, HandoffReason.OUT_OF_SCOPE)

        assert ticket.ticket_type.value == "ticketing"
        assert ticket.status.value == "dispatched"
        assert ticket.skill_group == "套餐业务组"
        assert ticket.conversation_id == conv.id
        assert "out_of_scope" in ticket.content

        db.expire_all()
        logs = (
            db.execute(select(AuditLog).where(AuditLog.action == "handoff.offline_callback"))
            .scalars()
            .all()
        )
        assert len(logs) == 1
        assert logs[0].detail["ticket_id"] == ticket.id
        assert logs[0].detail["skill_group"] == "套餐业务组"
