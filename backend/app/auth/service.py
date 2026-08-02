"""认证业务逻辑。

PRD 依据：实现决策 › 认证与会话（手机号 + 服务密码单因素认证）。
审计日志写入由 routes 层触发（循环3 接入），service 保持纯业务判定。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import verify_password
from app.models import Customer


def authenticate(db: Session, phone: str, service_password: str) -> Customer | None:
    """手机号 + 服务密码认证；通过返回 Customer，失败返回 None。"""
    customer = db.execute(select(Customer).where(Customer.phone == phone)).scalar_one_or_none()
    if customer is None:
        return None
    if not verify_password(service_password, customer.service_password_hash):
        return None
    return customer


def verify_service_password(customer: Customer, service_password: str) -> bool:
    """办理执行复核：校验当前客户的服务密码（CONTEXT › 办理执行复核）。

    复用 verify_password，但对象是已认证的当前客户（不查 phone），
    作为单因素认证的补偿控制 —— 防止会话被劫持后办理不可逆业务。
    """
    return verify_password(service_password, customer.service_password_hash)
