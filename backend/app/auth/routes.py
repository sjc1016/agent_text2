"""认证路由（/auth/login、/auth/reauth、/auth/me）。

PRD 依据：API 契约 /auth/login、/auth/reauth；ADR 0004。
循环2-3：/auth/login（成功颁 token，失败记审计）；reauth 循环5，/auth/me 循环4。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.audit import write_audit_log
from app.auth.dependencies import CurrentCustomer
from app.auth.schemas import (
    CustomerPublic,
    LoginRequest,
    ReauthRequest,
    ReauthResponse,
    TokenResponse,
)
from app.auth.security import create_access_token, create_execute_token, create_refresh_token
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
