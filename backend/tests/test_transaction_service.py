"""B6 循环2：办理类业务能力服务层测试（服务 seam）。

验收标准（issue #14）：
  - 办理类 tool 发起后推送 second.confirm 含结构化业务影响（套餐对比/生效时间/合约影响/
    费用变化），会话进入 In-Progress
  - 用户确认后创建 Ticket（Pending）入队，会话回退 Authenticated，未确认不入队
  - 办理类不直接生效，一律经 Ticket
  - Ticket 执行前推送 reauth.required，服务密码复核通过后 Processing→执行→Effective/Failed
  - 四类办理（套餐变更/增值订退/停机保号/充值缴费）均可发起

行为 SSOT：issue 验收标准 + PRD「测试决策 › tool 调用 seam / 调度任务 seam」。
本文件只测服务层逻辑（不测 WS 推送与 HTTP 契约，分别由 WS seam / HTTP seam 覆盖）。
"""

from __future__ import annotations

import pytest

from app.models import Conversation, Customer
from app.transaction.schemas import BusinessImpact
from app.transaction.service import (
    TRANSACTION_TYPES,
    confirm_transaction,
    execute_transaction,
    initiate_transaction,
    trigger_execution_reauth,
)


def _customer(db, phone: str = "13900000100") -> Customer:
    customer = Customer(phone=phone, service_password_hash="x")
    db.add(customer)
    db.commit()
    return customer


def _conversation(db, customer: Customer, status: str = "authenticated") -> Conversation:
    conv = Conversation(customer_id=customer.id, status=status)
    db.add(conv)
    db.commit()
    return conv


def _account(db, customer_id: int, plan_name: str = "畅享5G套餐", plan_price: float = 99.0):
    from datetime import date

    from app.models.inquiry import CustomerAccount

    account = CustomerAccount(
        customer_id=customer_id,
        balance=50.0,
        plan_name=plan_name,
        plan_price=plan_price,
        contract_expiry_date=date(2027, 6, 30),
    )
    db.add(account)
    db.commit()
    return account


def _plan(db, name: str = "畅享99套餐", price: float = 99.0):
    from app.models.general import Plan

    plan = Plan(name=name, price=price, data_allowance="30GB", call_minutes="1000分钟")
    db.add(plan)
    db.commit()
    return plan


# ---------------------------------------------------------------------------
# 验收1：发起后返回结构化业务影响（四要素），会话进入 In-Progress
# ---------------------------------------------------------------------------


class TestInitiateTransaction:
    def test_plan_change_initiate_returns_structured_impact(self, db):
        """套餐变更发起 → 影响含套餐对比/生效时间/合约影响/费用变化，会话进入 in_progress。"""
        customer = _customer(db)
        conv = _conversation(db, customer)
        _account(db, customer.id)
        _plan(db, name="畅享99套餐", price=99.0)

        impact = initiate_transaction(
            db, customer, conv, "plan_change", {"target_plan": "畅享99套餐"}
        )

        assert isinstance(impact, BusinessImpact)
        assert impact.transaction_type == "plan_change"
        assert "畅享5G套餐" in impact.plan_comparison
        assert "畅享99套餐" in impact.plan_comparison
        assert impact.effective_time
        assert impact.contract_impact
        assert "99" in impact.fee_change
        db.refresh(conv)
        assert conv.status == "in_progress"

    def test_plan_change_target_plan_missing_rejected(self, db):
        """目标套餐不存在 → ValueError（诚实拒绝，不编造）。"""
        customer = _customer(db)
        conv = _conversation(db, customer)
        _account(db, customer.id)

        with pytest.raises(ValueError, match="目标套餐不存在"):
            initiate_transaction(db, customer, conv, "plan_change", {"target_plan": "不存在的套餐"})

    def test_vadd_change_initiate_returns_impact(self, db):
        """增值业务订退发起 → 影响结构化，会话进入 in_progress。"""
        customer = _customer(db)
        conv = _conversation(db, customer)

        impact = initiate_transaction(
            db,
            customer,
            conv,
            "vadd_change",
            {"service_name": "彩铃", "action": "cancel"},
        )

        assert impact.transaction_type == "vadd_change"
        assert "彩铃" in impact.summary
        db.refresh(conv)
        assert conv.status == "in_progress"

    def test_suspend_hold_initiate_returns_impact(self, db):
        """停机保号发起 → 影响结构化。"""
        customer = _customer(db)
        conv = _conversation(db, customer)

        impact = initiate_transaction(db, customer, conv, "suspend_hold", {})

        assert impact.transaction_type == "suspend_hold"
        assert "停机" in impact.summary
        db.refresh(conv)
        assert conv.status == "in_progress"

    def test_recharge_initiate_returns_impact(self, db):
        """充值缴费发起 → 影响含金额与到账说明。"""
        customer = _customer(db)
        conv = _conversation(db, customer)

        impact = initiate_transaction(db, customer, conv, "recharge", {"amount": 100})

        assert impact.transaction_type == "recharge"
        assert "100" in impact.fee_change
        db.refresh(conv)
        assert conv.status == "in_progress"

    def test_all_four_transaction_types_supported(self):
        """四类办理（套餐变更/增值订退/停机保号/充值缴费）均在合法类型集内（验收5）。"""
        assert {
            "plan_change",
            "vadd_change",
            "suspend_hold",
            "recharge",
        } == TRANSACTION_TYPES

    def test_initiate_requires_authenticated_conversation(self, db):
        """会话非 authenticated（unauthenticated / in_progress）→ 拒绝发起。"""
        customer = _customer(db)
        conv = _conversation(db, customer, status="unauthenticated")

        with pytest.raises(ValueError, match="不可发起办理"):
            initiate_transaction(db, customer, conv, "recharge", {"amount": 50})

    def test_initiate_unknown_type_rejected(self, db):
        """未知办理类型 → ValueError。"""
        customer = _customer(db)
        conv = _conversation(db, customer)

        with pytest.raises(ValueError, match="未知办理类型"):
            initiate_transaction(db, customer, conv, "refund", {})

    def test_initiate_missing_params_rejected(self, db):
        """参数缺失（充值无金额）→ ValueError。"""
        customer = _customer(db)
        conv = _conversation(db, customer)

        with pytest.raises(ValueError, match="充值缴费需要金额"):
            initiate_transaction(db, customer, conv, "recharge", {})


# ---------------------------------------------------------------------------
# 验收2+3：确认后创建 Ticket(Pending) 入队，会话回退 Authenticated，未确认不入队
# ---------------------------------------------------------------------------


class TestConfirmTransaction:
    def test_confirm_creates_ticket_and_conversation_back_to_authenticated(self, db):
        """确认 → 创建办理类 Ticket(Pending)，会话回退 authenticated。"""
        from app.models import Ticket

        customer = _customer(db)
        conv = _conversation(db, customer)
        initiate_transaction(db, customer, conv, "recharge", {"amount": 100})

        ticket = confirm_transaction(db, customer, conv, "充值缴费 100 元")

        assert isinstance(ticket, Ticket)
        assert ticket.ticket_type.value == "transaction"
        assert ticket.status.value == "pending"
        assert ticket.customer_id == customer.id
        assert ticket.creator_id == customer.id
        assert ticket.content == "充值缴费 100 元"
        db.refresh(conv)
        assert conv.status == "authenticated"

    def test_unconfirmed_no_ticket_enqueued(self, db):
        """发起后未确认 → 无 Ticket 入队（未确认不入队，验收2）。"""
        from sqlalchemy import select

        from app.models import Ticket

        customer = _customer(db)
        conv = _conversation(db, customer)
        initiate_transaction(db, customer, conv, "suspend_hold", {})

        tickets = list(db.execute(select(Ticket)).scalars())
        assert tickets == []

    def test_confirm_requires_in_progress_conversation(self, db):
        """会话非 in_progress（authenticated）→ 拒绝确认。"""
        customer = _customer(db)
        conv = _conversation(db, customer)

        with pytest.raises(ValueError, match="不可确认办理"):
            confirm_transaction(db, customer, conv, "办理内容")

    def test_transaction_never_applies_directly(self, db):
        """办理一律经 Ticket：发起仅返回影响，确认后 Ticket 仍为 pending（不直接生效，验收3）。"""
        customer = _customer(db)
        conv = _conversation(db, customer)

        impact = initiate_transaction(db, customer, conv, "recharge", {"amount": 100})
        assert impact is not None  # 仅二次确认提示，无任何生效

        ticket = confirm_transaction(db, customer, conv, "充值缴费 100 元")
        assert ticket.status.value == "pending"  # 入队待执行，不直接生效


# ---------------------------------------------------------------------------
# 验收4：执行复核（调度 seam）→ 复核通过后 Processing → 执行 → Effective
# ---------------------------------------------------------------------------


class TestExecutionReauthAndExecute:
    def _pending_transaction_ticket(self, db, customer, content: str = "充值缴费 100 元"):
        from app.models import Ticket
        from app.models.ticket import TicketStatus, TicketType

        conv = _conversation(db, customer)
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

    def test_trigger_execution_reauth_passes_pending_ticket(self, db):
        """待执行办理类 Ticket → 调度 seam 通过（调用方负责推送 reauth.required）。"""
        customer = _customer(db)
        ticket = self._pending_transaction_ticket(db, customer)

        result = trigger_execution_reauth(db, customer, ticket)

        assert result.id == ticket.id

    def test_trigger_execution_reauth_rejects_non_pending(self, db):
        """非 pending（processing）→ 拒绝发起执行复核。"""
        from app.models import Ticket
        from app.models.ticket import TicketStatus, TicketType

        customer = _customer(db)
        conv = _conversation(db, customer)
        ticket = Ticket(
            conversation_id=conv.id,
            ticket_type=TicketType.TRANSACTION,
            status=TicketStatus.PROCESSING,
            content="办理",
            customer_id=customer.id,
            creator_type="customer",
            creator_id=customer.id,
        )
        db.add(ticket)
        db.commit()

        with pytest.raises(ValueError, match="不可发起执行复核"):
            trigger_execution_reauth(db, customer, ticket)

    def test_trigger_execution_reauth_rejects_other_customer(self, db):
        """非本人 Ticket → 拒绝（权限边界）。"""
        owner = _customer(db, phone="13900000101")
        other = _customer(db, phone="13900000102")
        ticket = self._pending_transaction_ticket(db, owner)

        with pytest.raises(ValueError, match="无权操作"):
            trigger_execution_reauth(db, other, ticket)

    def test_trigger_execution_reauth_rejects_ticketing_ticket(self, db):
        """工单类 Ticket → 不触发执行复核（仅办理类）。"""
        from app.models import Ticket
        from app.models.ticket import TicketStatus, TicketType

        customer = _customer(db)
        conv = _conversation(db, customer)
        ticket = Ticket(
            conversation_id=conv.id,
            ticket_type=TicketType.TICKETING,
            status=TicketStatus.PENDING,
            content="报修",
            customer_id=customer.id,
            creator_type="customer",
            creator_id=customer.id,
        )
        db.add(ticket)
        db.commit()

        with pytest.raises(ValueError, match="仅办理类工单"):
            trigger_execution_reauth(db, customer, ticket)

    def test_execute_transaction_reaches_effective(self, db):
        """复核通过后执行：pending → processing → effective（US-12）。"""
        customer = _customer(db)
        ticket = self._pending_transaction_ticket(db, customer)

        result = execute_transaction(db, ticket)

        assert result.id == ticket.id
        assert result.status.value == "effective"

    def test_execute_transaction_rejects_ticketing(self, db):
        """工单类 Ticket 不可执行（仅办理类）。"""
        from app.models import Ticket
        from app.models.ticket import TicketStatus, TicketType

        customer = _customer(db)
        conv = _conversation(db, customer)
        ticket = Ticket(
            conversation_id=conv.id,
            ticket_type=TicketType.TICKETING,
            status=TicketStatus.PENDING,
            content="报修",
            customer_id=customer.id,
            creator_type="customer",
            creator_id=customer.id,
        )
        db.add(ticket)
        db.commit()

        with pytest.raises(ValueError, match="仅办理类工单可执行"):
            execute_transaction(db, ticket)

    def test_execute_transaction_rejects_non_pending(self, db):
        """非 pending（effective 终态）→ 拒绝执行。"""
        from app.models import Ticket
        from app.models.ticket import TicketStatus, TicketType

        customer = _customer(db)
        conv = _conversation(db, customer)
        ticket = Ticket(
            conversation_id=conv.id,
            ticket_type=TicketType.TRANSACTION,
            status=TicketStatus.EFFECTIVE,
            content="已生效",
            customer_id=customer.id,
            creator_type="customer",
            creator_id=customer.id,
        )
        db.add(ticket)
        db.commit()

        with pytest.raises(ValueError, match="不可执行"):
            execute_transaction(db, ticket)

    def test_execute_flow_preserves_ticket_content(self, db):
        """执行不改变 Ticket 内容与归属（仅状态流转）。"""
        customer = _customer(db)
        ticket = self._pending_transaction_ticket(db, customer, content="将套餐变更为畅享99套餐")

        execute_transaction(db, ticket)

        db.refresh(ticket)
        assert ticket.content == "将套餐变更为畅享99套餐"
        assert ticket.customer_id == customer.id
