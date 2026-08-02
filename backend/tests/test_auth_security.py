"""B1 循环4：JWT 过期时间与 claim（access 2h / refresh 7d）。

验收标准（issue #4）：
  JWT access 2h / refresh 7d 过期时间正确
  （PRD 依据：实现决策 › 认证与会话；ADR 0004）

单元测试：解码 token 验证 exp 与 type claim（不经过 HTTP，聚焦 JWT 契约）。
"""

from __future__ import annotations

from datetime import datetime, timezone

import jwt

from app.auth.security import create_access_token, create_execute_token, create_refresh_token
from app.config import get_settings

_settings = get_settings()


def _decode_exp(token: str) -> datetime:
    payload = jwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])
    return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)


def test_access_token_expires_in_2h():
    before = datetime.now(timezone.utc)
    token = create_access_token(42)
    exp = _decode_exp(token)
    after = datetime.now(timezone.utc)

    delta = exp - before
    # access 2h = 7200s；扣除 before→签发→after 的耗时，余量应落在 (7140, 7200]
    assert 7140 <= delta.total_seconds() <= 7200
    assert exp <= after + __import__("datetime").timedelta(hours=2)


def test_refresh_token_expires_in_7d():
    before = datetime.now(timezone.utc)
    token = create_refresh_token(42)
    exp = _decode_exp(token)

    delta = exp - before
    # refresh 7d = 604800s；允许 ±60s 误差
    assert 604740 <= delta.total_seconds() <= 604800


def test_access_token_has_type_and_sub_claim():
    token = create_access_token(42)
    payload = jwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])
    assert payload["type"] == "access"
    assert payload["sub"] == "42"


def test_refresh_token_has_type_claim():
    token = create_refresh_token(42)
    payload = jwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])
    assert payload["type"] == "refresh"


def test_execute_token_expires_in_10min():
    """execute token 短期（10min，CONTEXT › 办理执行复核）—— 补偿控制凭证。"""
    before = datetime.now(timezone.utc)
    token = create_execute_token(42)
    exp = _decode_exp(token)

    delta = exp - before
    # execute 10min = 600s；允许 ±60s 误差
    assert 540 <= delta.total_seconds() <= 600


def test_execute_token_has_type_execute_claim():
    """execute token type=execute —— 不能被当作 access token 用（get_current_customer 拒绝）。"""
    token = create_execute_token(42)
    payload = jwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])
    assert payload["type"] == "execute"
    assert payload["sub"] == "42"
