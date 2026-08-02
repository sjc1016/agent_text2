"""密码哈希与 JWT 签发/校验。

ADR 0004：bcrypt 成本 12（直接用 bcrypt 库，passlib 已废弃且与 bcrypt 5+ 不兼容）；
JWT 无状态（access 2h / refresh 7d），HS256。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Customer

_settings = get_settings()


def hash_password(password: str) -> str:
    """bcrypt 哈希（成本 12，ADR 0004）。"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_settings.bcrypt_cost)).decode()


def verify_password(password: str, hashed: str) -> bool:
    """校验明文密码与 bcrypt hash。"""
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _create_token(subject: str, expires_in: timedelta, token_type: str) -> str:
    expire = datetime.now(timezone.utc) + expires_in
    payload = {"sub": subject, "exp": expire, "type": token_type}
    return jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


def create_access_token(customer_id: int) -> str:
    """access token（2h，ADR 0004）。"""
    return _create_token(
        str(customer_id), timedelta(minutes=_settings.access_token_expire_minutes), "access"
    )


def create_refresh_token(customer_id: int) -> str:
    """refresh token（7d，ADR 0004）。"""
    return _create_token(
        str(customer_id), timedelta(days=_settings.refresh_token_expire_days), "refresh"
    )


def create_execute_token(customer_id: int) -> str:
    """execute token（短期，CONTEXT › 办理执行复核）。

    办理类 Ticket 执行前复核通过后颁发，作为单因素认证的补偿控制凭证；
    type=execute，仅用于触发 Ticket 执行一步，过期后需重新复核。
    """
    return _create_token(
        str(customer_id),
        timedelta(minutes=_settings.execute_token_expire_minutes),
        "execute",
    )


def decode_token(token: str) -> dict[str, object]:
    """解码并校验 JWT；非法/过期抛 jwt 异常（由调用方转 HTTP 401）。"""
    return jwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])


def get_customer_by_id(db: Session, customer_id: int) -> Customer | None:
    """按主键查客户（供鉴权依赖复用）。"""
    return db.get(Customer, customer_id)
