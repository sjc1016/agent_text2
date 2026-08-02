"""B5 REST `/inquiries/*` 测试（验收标准3+4，HTTP 集成 seam）。

PRD 依据：
  - 验收标准3：未认证调用 `/inquiries/*` 拒绝（401/403）
    （PRD 依据：`CONTEXT.md › 业务能力 / 查询类`；`PRD 测试决策 › HTTP 集成 seam`）
  - 验收标准4：敏感数据访问（话费/合约/号码）写入审计日志
    （PRD 依据：`CONTEXT.md › 审计日志`；`用户故事 US-3, US-6`）
  - 实现决策 › API 契约（/inquiries/* 查询类业务能力；REST 用 JWT Authorization header）

鉴权：复用 B1 的 CurrentCustomer（Authorization header Bearer），无凭据 → 401。
"""

from __future__ import annotations

from datetime import date

import bcrypt
import pytest

pytestmark = pytest.mark.integration


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def _seed_account(db, customer_id: int, **overrides) -> None:
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


async def _login(db_client, db, phone: str = "13900000020", password: str = "svc12345"):
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


class TestInquiryAuthBoundary:
    """验收标准3：未认证调用 /inquiries/* 拒绝（HTTP 集成 seam）。"""

    async def test_balance_unauthenticated_returns_401(self, db_client, db):
        """无 Authorization header 访问 /inquiries/balance → 401。"""
        resp = await db_client.get("/inquiries/balance")
        assert resp.status_code == 401

    async def test_all_endpoints_unauthenticated_returns_401(self, db_client, db):
        """其余查询端点未认证均 401（同一边界）。"""
        for path in (
            "/inquiries/plan",
            "/inquiries/usage",
            "/inquiries/contract",
            "/inquiries/value-added-services",
        ):
            resp = await db_client.get(path)
            assert resp.status_code == 401, path


class TestInquiryEndpoints:
    """认证客户查询返回正确数据（验收标准1+2 的 REST seam）。"""

    async def test_balance_returns_balance(self, db_client, db):
        customer, token = await _login(db_client, db, phone="13900000021")
        _seed_account(db, customer.id, balance=128.50)

        resp = await db_client.get(
            "/inquiries/balance", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["phone"] == "13900000021"
        assert body["balance"] == 128.50

    async def test_plan_returns_plan(self, db_client, db):
        customer, token = await _login(db_client, db, phone="13900000022")
        _seed_account(db, customer.id, plan_name="畅享5G套餐", plan_price=99.0)

        resp = await db_client.get("/inquiries/plan", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["plan_name"] == "畅享5G套餐"
        assert body["plan_price"] == 99.0

    async def test_usage_returns_usage(self, db_client, db):
        customer, token = await _login(db_client, db, phone="13900000023")
        _seed_account(db, customer.id, call_used="320分钟", data_used="18.5GB")

        resp = await db_client.get("/inquiries/usage", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["call_used"] == "320分钟"
        assert body["data_used"] == "18.5GB"

    async def test_contract_returns_expiry(self, db_client, db):
        customer, token = await _login(db_client, db, phone="13900000024")
        _seed_account(db, customer.id, contract_expiry_date=date(2027, 6, 30))

        resp = await db_client.get(
            "/inquiries/contract", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert resp.json()["contract_expiry_date"] == "2027-06-30"

    async def test_value_added_returns_subscriptions(self, db_client, db):
        from app.models.inquiry import CustomerValueAddedService

        customer, token = await _login(db_client, db, phone="13900000025")
        _seed_account(db, customer.id)
        db.add(
            CustomerValueAddedService(
                customer_id=customer.id,
                service_name="彩铃",
                monthly_fee=5.0,
                status="active",
            )
        )
        db.commit()

        resp = await db_client.get(
            "/inquiries/value-added-services",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list) and len(data) == 1
        assert data[0]["service_name"] == "彩铃"

    async def test_balance_no_account_returns_404(self, db_client, db):
        """无账户记录 → 404（不编造，HTTP 语义）。"""
        customer, token = await _login(db_client, db, phone="13900000026")

        resp = await db_client.get(
            "/inquiries/balance", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 404


class TestInquiryAudit:
    """验收标准4：敏感数据访问（话费/合约/号码）写入审计日志。"""

    async def test_sensitive_queries_write_audit_log(self, db_client, db):
        """话费（US-3）与合约（US-6）查询写 inquiry.* 审计，含号码留痕。"""
        from app.models import AuditLog

        customer, token = await _login(db_client, db, phone="13900000027")
        _seed_account(db, customer.id)

        for path in ("/inquiries/balance", "/inquiries/contract"):
            resp = await db_client.get(path, headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200

        logs = (
            db.query(AuditLog)
            .filter(
                AuditLog.actor_type == "customer",
                AuditLog.actor_id == customer.id,
                AuditLog.action.like("inquiry.%"),
            )
            .all()
        )
        assert len(logs) == 2
        assert {log.action for log in logs} == {"inquiry.balance", "inquiry.contract"}
        assert all(log.detail["phone"] == "13900000027" for log in logs)
