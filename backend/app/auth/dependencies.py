"""鉴权依赖：从 Authorization header 解析 JWT → 返回当前 Customer。

深模块：把 token 提取、解码、类型校验、客户查找与 HTTP 错误转换封装为单一依赖，
路由层只需 `Depends(get_current_customer)` 即可受保护 —— 接口小（一个依赖），
实现深（5 步校验链）。

PRD 依据：实现决策 › 认证与会话（JWT 无状态鉴权）；ADR 0004。
循环4（验收3）：REST Authorization header 鉴权生效。
"""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_token, get_agent_by_id, get_customer_by_id
from app.db import get_db
from app.models import Customer, User

# auto_error=False：缺失/格式错由本依赖统一转 401（而非 HTTPBearer 默认 403），
# 与 CONTEXT › 认证语义「无凭据 → 401」一致。
bearer_scheme = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]
BearerCreds = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def get_current_customer(db: DbSession, credentials: BearerCreds) -> Customer:
    """解析 Bearer token → 校验 access 类型 → 返回 Customer；任一步失败 → 401。

    校验链：
      1. Authorization: Bearer 存在且 scheme 正确
      2. JWT 签名/过期合法（decode_token 内部校验）
      3. token type == access（拒绝 refresh token 访问受保护端点）
      4. sub claim 可解析为 customer_id
      5. Customer 存在
    """
    _unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未提供有效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized

    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise _unauthorized from exc

    if payload.get("type") != "access":
        raise _unauthorized

    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise _unauthorized
    try:
        customer_id = int(sub)
    except ValueError as exc:
        raise _unauthorized from exc

    customer = get_customer_by_id(db, customer_id)
    if customer is None:
        raise _unauthorized

    return customer


# 受保护端点的统一鉴权写法：`current: CurrentCustomer` 即可。
CurrentCustomer = Annotated[Customer, Depends(get_current_customer)]


def get_current_agent(db: DbSession, credentials: BearerCreds) -> User:
    """解析 Bearer token → 校验 agent_access 类型 → 返回坐席账号 User；任一步失败 → 401。

    与 get_current_customer 同构，差异仅在 token type（agent_access）与主体表
    （users 坐席账号）。客户 access token 访问坐席端点 → 401（主体隔离）。
    """
    _unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未提供有效的坐席认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized

    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise _unauthorized from exc

    if payload.get("type") != "agent_access":
        raise _unauthorized

    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise _unauthorized
    try:
        agent_id = int(sub)
    except ValueError as exc:
        raise _unauthorized from exc

    agent = get_agent_by_id(db, agent_id)
    if agent is None:
        raise _unauthorized

    return agent


# 坐席受保护端点的统一鉴权写法：`current: CurrentAgent` 即可。
CurrentAgent = Annotated[User, Depends(get_current_agent)]


def get_current_execute_customer(db: DbSession, credentials: BearerCreds) -> Customer:
    """解析 Bearer token → 校验 execute 类型 → 返回 Customer；任一步失败 → 401。

    校验链与 get_current_customer 同构，差异仅在 token type（execute）：
    execute token 由 /auth/reauth（办理执行复核，B1）颁发，仅用于触发办理类
    Ticket 执行一步（CONTEXT › 办理执行复核）；access token 调执行端点 → 401
    （未复核不得执行，作为单因素认证的补偿控制）。
    """
    _unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未提供有效的执行复核凭证（请先 /auth/reauth 完成服务密码复核）",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized

    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise _unauthorized from exc

    if payload.get("type") != "execute":
        raise _unauthorized

    sub = payload.get("sub")
    if not isinstance(sub, str):
        raise _unauthorized
    try:
        customer_id = int(sub)
    except ValueError as exc:
        raise _unauthorized from exc

    customer = get_customer_by_id(db, customer_id)
    if customer is None:
        raise _unauthorized

    return customer


# 办理执行（execute token）受保护端点的统一鉴权写法：`current: CurrentExecuteCustomer` 即可。
CurrentExecuteCustomer = Annotated[Customer, Depends(get_current_execute_customer)]
