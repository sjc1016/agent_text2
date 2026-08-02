"""B6 循环3：办理类 tool 调用 seam 测试（验收1+5，与 LLM 解耦）。

验收标准（issue #14）：
  - 办理类 tool 发起后返回含结构化业务影响（套餐对比/生效时间/合约影响/费用变化）
    的二次确认标记，会话进入 In-Progress（PRD 依据：`PRD 测试决策 › tool 调用 seam`；
    `用户故事 US-8~US-11`）
  - 四类办理（套餐变更/增值订退/停机保号/充值缴费）均可发起

行为 SSOT：issue 验收标准 + PRD「测试决策 › tool 调用 seam」
（LangChain tools 作为纯函数测试，与 LLM 调用解耦）。
"""

from __future__ import annotations

import json

from app.agent.tools import ToolContext, ToolRegistry
from app.transaction.tools import register_transaction_tools


def _customer(db, phone: str = "13900000200"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash="x")
    db.add(customer)
    db.commit()
    return customer


def _conversation(db, customer, status: str = "authenticated"):
    from app.models import Conversation

    conv = Conversation(customer_id=customer.id, status=status)
    db.add(conv)
    db.commit()
    return conv


def _account(db, customer_id: int):
    from app.models.inquiry import CustomerAccount

    account = CustomerAccount(
        customer_id=customer_id,
        balance=50.0,
        plan_name="畅享5G套餐",
        plan_price=99.0,
    )
    db.add(account)
    db.commit()
    return account


def _plan(db, name: str = "畅享99套餐", price: float = 99.0):
    from app.models.general import Plan

    db.add(Plan(name=name, price=price, data_allowance="30GB", call_minutes="1000分钟"))
    db.commit()


class TestTransactionTools:
    def test_plan_change_tool_returns_confirmation_marker(self, db):
        """套餐变更 tool → 返回 awaiting_confirmation 标记 + 结构化业务影响。"""
        customer = _customer(db)
        conv = _conversation(db, customer)
        _account(db, customer.id)
        _plan(db)

        registry = ToolRegistry()
        register_transaction_tools(registry)
        result = registry.invoke(
            "plan_change",
            ToolContext(
                customer_id=customer.id,
                conversation_id=conv.id,
                db=db,
                params={"target_plan": "畅享99套餐"},
            ),
        )

        data = json.loads(result)
        assert data["status"] == "awaiting_confirmation"
        assert data["transaction_type"] == "plan_change"
        impact = data["business_impact"]
        for key in [
            "summary",
            "plan_comparison",
            "effective_time",
            "contract_impact",
            "fee_change",
        ]:
            assert impact[key]
        db.refresh(conv)
        assert conv.status == "in_progress"

    def test_vadd_change_tool_returns_confirmation_marker(self, db):
        """增值业务订退 tool → 二次确认标记。"""
        customer = _customer(db)
        conv = _conversation(db, customer)

        registry = ToolRegistry()
        register_transaction_tools(registry)
        result = registry.invoke(
            "vadd_change",
            ToolContext(
                customer_id=customer.id,
                conversation_id=conv.id,
                db=db,
                params={"service_name": "彩铃", "action": "cancel"},
            ),
        )

        data = json.loads(result)
        assert data["status"] == "awaiting_confirmation"
        assert data["transaction_type"] == "vadd_change"
        assert "彩铃" in data["business_impact"]["summary"]

    def test_suspend_hold_tool_returns_confirmation_marker(self, db):
        """停机保号 tool → 二次确认标记。"""
        customer = _customer(db)
        conv = _conversation(db, customer)

        registry = ToolRegistry()
        register_transaction_tools(registry)
        result = registry.invoke(
            "suspend_hold",
            ToolContext(customer_id=customer.id, conversation_id=conv.id, db=db),
        )

        data = json.loads(result)
        assert data["status"] == "awaiting_confirmation"
        assert data["transaction_type"] == "suspend_hold"

    def test_recharge_tool_returns_confirmation_marker(self, db):
        """充值缴费 tool → 二次确认标记，影响含金额。"""
        customer = _customer(db)
        conv = _conversation(db, customer)

        registry = ToolRegistry()
        register_transaction_tools(registry)
        result = registry.invoke(
            "recharge",
            ToolContext(
                customer_id=customer.id,
                conversation_id=conv.id,
                db=db,
                params={"amount": 100},
            ),
        )

        data = json.loads(result)
        assert data["status"] == "awaiting_confirmation"
        assert data["transaction_type"] == "recharge"
        assert "100" in data["business_impact"]["fee_change"]

    def test_tool_rejects_unauthenticated(self, db):
        """未认证（无 customer_id）→ 诚实拒绝，不进入二次确认。"""
        customer = _customer(db)
        conv = _conversation(db, customer)

        registry = ToolRegistry()
        register_transaction_tools(registry)
        result = registry.invoke(
            "recharge",
            ToolContext(conversation_id=conv.id, db=db, params={"amount": 100}),
        )

        assert "认证" in result
        assert "awaiting_confirmation" not in result

    def test_tool_rejects_invalid_params_with_clear_message(self, db):
        """参数缺失 → 返回错误说明（不进入二次确认）。"""
        customer = _customer(db)
        conv = _conversation(db, customer)

        registry = ToolRegistry()
        register_transaction_tools(registry)
        result = registry.invoke(
            "recharge",
            ToolContext(customer_id=customer.id, conversation_id=conv.id, db=db),
        )

        assert "金额" in result
        assert "awaiting_confirmation" not in result

    def test_tool_rejects_non_authenticated_conversation(self, db):
        """会话未认证 → 拒绝发起（办理需 authenticated 会话）。"""
        customer = _customer(db)
        conv = _conversation(db, customer, status="unauthenticated")

        registry = ToolRegistry()
        register_transaction_tools(registry)
        result = registry.invoke(
            "recharge",
            ToolContext(
                customer_id=customer.id,
                conversation_id=conv.id,
                db=db,
                params={"amount": 100},
            ),
        )

        assert "不可发起办理" in result
        assert "awaiting_confirmation" not in result

    def test_tool_audits_initiate(self, db):
        """发起动作经 audit_hook 记录（CONTEXT › 审计日志：办理类发起）。"""
        customer = _customer(db)
        conv = _conversation(db, customer)
        events: list[dict] = []

        registry = ToolRegistry()
        register_transaction_tools(registry)
        registry.invoke(
            "suspend_hold",
            ToolContext(
                customer_id=customer.id,
                conversation_id=conv.id,
                db=db,
                audit_hook=events.append,
            ),
        )

        assert any(e.get("type") == "transaction.initiate" for e in events)

    def test_all_four_tools_registered(self, db):
        """四类办理 tool 全部注册进 ToolRegistry。"""
        registry = ToolRegistry()
        register_transaction_tools(registry)
        names = {t.name for t in registry.list_tools()}
        assert {"plan_change", "vadd_change", "suspend_hold", "recharge"} <= names
