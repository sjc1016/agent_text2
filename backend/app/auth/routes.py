"""认证路由（/auth/login、/auth/refresh、/auth/reauth、/auth/me）。

PRD 依据：API 契约 /auth/login、/auth/reauth；ADR 0004。
循环2-3：/auth/login（成功颁 token，失败记审计）；reauth 循环5，/auth/me 循环4。
issue #65：/auth/refresh（access 2h 过期后用 7d refresh token 换新 access token，
前端 401 拦截自动刷新，避免假已认证态下消息被静默吞掉）。
"""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.audit import write_audit_log
from app.auth.dependencies import CurrentCustomer
from app.auth.schemas import (
    CustomerPublic,
    LoginRequest,
    ReauthRequest,
    ReauthResponse,
    RefreshRequest,
    RefreshResponse,
    TokenResponse,
)
from app.auth.security import (
    create_access_token,
    create_execute_token,
    create_refresh_token,
    decode_token,
)
from app.auth.service import authenticate, verify_service_password
from app.db import get_db
from app.models import Customer

router = APIRouter(prefix="/auth", tags=["auth"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    """服务密码登录 → 颁发 access/refresh token；成功/失败均记审计日志（CONTEXT › 审计日志）。"""
    customer = authenticate(db, payload.phone, payload.service_password)
    if customer is None:
        write_audit_log(
            db,
            actor_type="customer",
            action="auth.login.failure",
            detail={"phone": payload.phone},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="手机号或服务密码错误",
        )
    write_audit_log(
        db,
        actor_type="customer",
        actor_id=customer.id,
        action="auth.login.success",
    )
    return TokenResponse(
        access_token=create_access_token(customer.id),
        refresh_token=create_refresh_token(customer.id),
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh(payload: RefreshRequest, db: DbSession) -> RefreshResponse:
    """用 refresh token（7d，type=refresh）换发新 access token（issue #65）。

    前端在受保护端点收到凭证 401（WWW-Authenticate: Bearer）时调用本端点：
    refresh token 有效 → 颁发新 access token（原 refresh token 继续有效，不轮换，
    保持 v1 无状态简单语义）；无效/过期/类型不符/主体不存在 → 401，前端应
    清除凭证回访客态（refresh 失败即登录过期）。
    """
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="刷新凭证无效或已过期，请重新登录",
    )
    try:
        claims = decode_token(payload.refresh_token)
    except jwt.PyJWTError as exc:
        raise invalid from exc

    if claims.get("type") != "refresh":
        raise invalid
    sub = claims.get("sub")
    if not isinstance(sub, str):
        raise invalid
    try:
        customer_id = int(sub)
    except ValueError as exc:
        raise invalid from exc
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise invalid
    return RefreshResponse(access_token=create_access_token(customer.id))


@router.get("/me", response_model=CustomerPublic)
def read_current_user(current: CurrentCustomer) -> Customer:
    """返回当前认证客户的公开档案（受保护端点）。

    response_model=CustomerPublic 负责过滤敏感字段（service_password_hash 等）。
    PRD 依据：实现决策 › 认证与会话；循环4（验收3）。
    """
    return current


@router.post("/reauth", response_model=ReauthResponse)
def reauth(payload: ReauthRequest, db: DbSession, current: CurrentCustomer) -> ReauthResponse:
    """办理执行复核：再次校验服务密码 → 颁发短期 execute_token。

    CONTEXT › 办理执行复核 (Transaction Re-auth)：办理类 Ticket 执行前的补偿控制。
    受 access token 保护（current 已认证），此处复核服务密码本身；成功/失败均记审计。
    PRD 依据：实现决策 › 认证与会话 / 办理执行复核；循环5（验收4）。
    """
    if not verify_service_password(current, payload.service_password):
        write_audit_log(
            db,
            actor_type="customer",
            actor_id=current.id,
            action="auth.reauth.failure",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="服务密码错误",
        )
    write_audit_log(
        db,
        actor_type="customer",
        actor_id=current.id,
        action="auth.reauth.success",
    )
    return ReauthResponse(execute_token=create_execute_token(current.id))
