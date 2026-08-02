"""B5 查询类业务能力 tool 测试（验收标准1+2，tool 调用 seam）。

PRD 依据：
  - 验收标准1：话费余额查询返回当前账户余额
    （PRD 依据：`PRD 实现决策 › API 契约 /inquiries/*`；
    `PRD 测试决策 › tool 调用 seam`；`用户故事 US-3`）
  - 验收标准2：当前套餐详情、用量、合约到期、已订购增值业务四类查询分别返回正确数据
    （PRD 依据：`PRD 测试决策 › tool 调用 seam`；`用户故事 US-4~US-7`）
  - 验收标准4：敏感数据访问（话费/合约/号码）写入审计日志
    （PRD 依据：`CONTEXT.md › 审计日志`；`用户故事 US-3, US-6`）

行为 SSOT：issue 验收标准 + PRD「测试决策 › tool 调用 seam」
（LangChain tools 作为纯函数测试，与 LLM 调用解耦）。
"""

from __future__ import annotations

from app.agent.inquiry_tools import register_inquiry_tools
from app.agent.tools import ToolContext, ToolRegistry


def _seed_account(db, customer_id: int, **overrides) -> None:
    """播种客户账户数据（customer_accounts 1:1 于 Customer）。"""
    from datetime import date

    from app.models.inquiry import CustomerAccount

    defaults = {
        "customer_id": customer_id,
        "balance": 128.50,
        "plan_name": "畅享5G套餐",
        "plan_price": 99.0,
        "call_used": "320分钟",
        "data_used": "18.5GB",
        "contract_expiry_date": date(2027, 6, 30),
    }
    defaults.update(overrides)
    db.add(CustomerAccount(**defaults))
    db.commit()


class TestBalanceLookupTool:
    """验收标准1：话费余额查询返回当前账户余额（US-3）。"""

    def test_balance_lookup_returns_balance(self, db):
        """认证客户查询话费余额 → 返回当前余额金额。"""
        from app.models import Customer

        customer = Customer(phone="13900000001", service_password_hash="x")
        db.add(customer)
        db.commit()
        _seed_account(db, customer.id, balance=128.50)

        registry = ToolRegistry()
        register_inquiry_tools(registry)
        result = registry.invoke(
            "balance_lookup",
            ToolContext(customer_id=customer.id, db=db),
        )
        assert "128.5" in result or "128.50" in result
        assert "话费" in result

    def test_balance_lookup_rejects_unauthenticated(self, db):
        """未认证（Visitor，无 customer_id）→ 拒绝查询（CONTEXT › 查询类需认证）。"""
        registry = ToolRegistry()
        register_inquiry_tools(registry)
        result = registry.invoke(
            "balance_lookup",
            ToolContext(db=db),
        )
        assert "认证" in result

    def test_balance_lookup_no_account_replies_honestly(self, db):
        """无账户记录 → 诚实回复未查询到（不编造）。"""
        registry = ToolRegistry()
        register_inquiry_tools(registry)
        result = registry.invoke(
            "balance_lookup",
            ToolContext(customer_id=999, db=db),
        )
        assert "未查询到" in result


# ---------------------------------------------------------------------------
# 循环2-5：验收标准2 — 四类查询（套餐详情 / 用量 / 合约到期 / 增值业务）
# PRD 依据：`PRD 测试决策 › tool 调用 seam`；`用户故事 US-4~US-7`
# ---------------------------------------------------------------------------


class TestPlanDetailLookupTool:
    """当前套餐详情查询（US-4）。"""

    def test_plan_detail_lookup_returns_current_plan(self, db):
        from app.models import Customer

        customer = Customer(phone="13900000002", service_password_hash="x")
        db.add(customer)
        db.commit()
        _seed_account(db, customer.id, plan_name="畅享5G套餐", plan_price=99.0)

        registry = ToolRegistry()
        register_inquiry_tools(registry)
        result = registry.invoke(
            "plan_detail_lookup",
            ToolContext(customer_id=customer.id, db=db),
        )
        assert "畅享5G套餐" in result
        assert "99" in result

    def test_plan_detail_lookup_no_account_replies_honestly(self, db):
        """无账户记录 → 诚实回复未查询到（不编造）。"""
        registry = ToolRegistry()
        register_inquiry_tools(registry)
        result = registry.invoke(
            "plan_detail_lookup",
            ToolContext(customer_id=999, db=db),
        )
        assert "未查询到" in result


class TestUsageLookupTool:
    """通话/流量使用量查询（US-5）。"""

    def test_usage_lookup_returns_usage(self, db):
        from app.models import Customer

        customer = Customer(phone="13900000003", service_password_hash="x")
        db.add(customer)
        db.commit()
        _seed_account(db, customer.id, call_used="320分钟", data_used="18.5GB")

        registry = ToolRegistry()
        register_inquiry_tools(registry)
        result = registry.invoke(
            "usage_lookup",
            ToolContext(customer_id=customer.id, db=db),
        )
        assert "320分钟" in result
        assert "18.5GB" in result


class TestContractLookupTool:
    """合约到期时间查询（US-6）。"""

    def test_contract_lookup_returns_expiry(self, db):
        from datetime import date

        from app.models import Customer

        customer = Customer(phone="13900000004", service_password_hash="x")
        db.add(customer)
        db.commit()
        _seed_account(db, customer.id, contract_expiry_date=date(2027, 6, 30))

        registry = ToolRegistry()
        register_inquiry_tools(registry)
        result = registry.invoke(
            "contract_lookup",
            ToolContext(customer_id=customer.id, db=db),
        )
        assert "2027-06-30" in result

    def test_contract_lookup_no_account_replies_honestly(self, db):
        """无账户记录 → 诚实回复未查询到（不编造）。"""
        registry = ToolRegistry()
        register_inquiry_tools(registry)
        result = registry.invoke(
            "contract_lookup",
            ToolContext(customer_id=999, db=db),
        )
        assert "未查询到" in result


class TestValueAddedLookupTool:
    """已订购增值业务查询（US-7）。"""

    def test_value_added_lookup_returns_subscriptions(self, db):
        from app.models import Customer
        from app.models.inquiry import CustomerValueAddedService

        customer = Customer(phone="13900000005", service_password_hash="x")
        db.add(customer)
        db.commit()
        db.add_all(
            [
                CustomerValueAddedService(
                    customer_id=customer.id,
                    service_name="彩铃",
                    monthly_fee=5.0,
                    status="active",
                ),
                CustomerValueAddedService(
                    customer_id=customer.id,
                    service_name="来电显示",
                    monthly_fee=3.0,
                    status="active",
                ),
            ]
        )
        db.commit()

        registry = ToolRegistry()
        register_inquiry_tools(registry)
        result = registry.invoke(
            "value_added_lookup",
            ToolContext(customer_id=customer.id, db=db),
        )
        assert "彩铃" in result
        assert "来电显示" in result

    def test_value_added_lookup_empty_replies_honestly(self, db):
        """无已订购增值业务 → 诚实回复无订阅（不编造）。"""
        from app.models import Customer

        customer = Customer(phone="13900000006", service_password_hash="x")
        db.add(customer)
        db.commit()
        _seed_account(db, customer.id)

        registry = ToolRegistry()
        register_inquiry_tools(registry)
        result = registry.invoke(
            "value_added_lookup",
            ToolContext(customer_id=customer.id, db=db),
        )
        assert "未" in result
