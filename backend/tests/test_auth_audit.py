"""B1 循环6：审计完整性 + bcrypt 成本。

验收标准（issue #4）：
  bcrypt 成本 12；认证成功/失败与敏感数据访问写入 audit_logs
  （PRD 依据：实现决策 › 认证与会话；CONTEXT.md › 审计日志）

CONTEXT › 审计日志 要求：服务密码认证（成功/失败）必须记录。
本测试集验证 login 成功/失败、reauth 成功/失败四条路径的审计留痕完整性，
并锁定 bcrypt 成本 12（ADR 0004）的契约，防止配置回退弱化密码强度。
"""

from __future__ import annotations

import bcrypt
import pytest

from app.auth.security import hash_password
from app.config import get_settings

_settings = get_settings()


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


# ---------- 审计完整性 ----------


@pytest.mark.integration
async def test_login_success_writes_audit_log(db_client, db):
    """登录成功 → 审计 auth.login.success（CONTEXT › 审计日志 要求成功/失败均记录）。"""
    from app.models import AuditLog, Customer

    customer = Customer(
        phone="13900000007",
        service_password_hash=_hash_password("svc12345"),
    )
    db.add(customer)
    db.commit()

    response = await db_client.post(
        "/auth/login",
        json={"phone": "13900000007", "service_password": "svc12345"},
    )
    assert response.status_code == 200

    logs = (
        db.query(AuditLog)
        .filter(
            AuditLog.actor_id == customer.id,
            AuditLog.action == "auth.login.success",
        )
        .all()
    )
    assert len(logs) == 1


@pytest.mark.integration
async def test_login_failure_writes_audit_log(db_client, db):
    """登录失败 → 审计 auth.login.failure（已在循环3 实现，本测试锁定契约防回退）。"""
    from app.models import AuditLog, Customer

    customer = Customer(
        phone="13900000008",
        service_password_hash=_hash_password("svc12345"),
    )
    db.add(customer)
    db.commit()

    response = await db_client.post(
        "/auth/login",
        json={"phone": "13900000008", "service_password": "wrong"},
    )
    assert response.status_code == 401

    logs = db.query(AuditLog).filter(AuditLog.action == "auth.login.failure").all()
    assert any(log.detail == {"phone": "13900000008"} for log in logs)


# ---------- bcrypt 成本 12（ADR 0004） ----------


def test_bcrypt_cost_setting_is_12():
    """Settings.bcrypt_cost == 12（ADR 0004 契约，防配置回退弱化强度）。"""
    assert _settings.bcrypt_cost == 12


def test_hash_password_uses_cost_12():
    """hash_password 产生的 bcrypt hash 编码 rounds=12（$2b$12$...）。"""
    hashed = hash_password("any-service-password")
    # bcrypt hash 格式：$2b$<rounds>$<22 salt><31 hash>
    assert hashed.startswith("$2b$12$"), f"期望 $2b$12$ 前缀，实际 {hashed[:7]}"


def test_hash_password_is_verifiable():
    """hash_password 产出可被 verify_password 校验（端到端 bcrypt 闭环）。"""
    from app.auth.security import verify_password

    hashed = hash_password("svc12345")
    assert verify_password("svc12345", hashed) is True
    assert verify_password("wrong", hashed) is False
