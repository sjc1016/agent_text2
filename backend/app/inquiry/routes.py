"""查询类业务能力 REST 路由（Customer 认证，US-3~US-7）。

PRD 依据：
  - 实现决策 › API 契约（/inquiries/* 查询类业务能力；REST 用 JWT Authorization header）
  - 测试决策 › HTTP 集成 seam（请求/响应形状、状态码、鉴权边界）
  - CONTEXT.md › 业务能力 / 查询类（只读，Customer 认证后可直接调用）
  - CONTEXT.md › 审计日志（敏感数据访问：话费、合约、号码 必须记录）
  - 用户故事 US-3~US-7

设计说明（与 tool 调用 seam 对称）：
  - 端点复用 inquiry.service 的查询函数，不重复实现数据访问逻辑；
  - 一律挂 CurrentCustomer（B1 鉴权依赖）：无凭据 → 401（验收标准3）；
  - 无账户记录 → 404（不编造，HTTP 语义）；
  - 每次查询写审计（actor_type=customer，action=inquiry.*，detail 含号码留痕）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.audit import write_audit_log
from app.auth.dependencies import CurrentCustomer
from app.db import get_db
from app.inquiry.schemas import (
    InquiryBalanceOut,
    InquiryContractOut,
    InquiryPlanOut,
    InquiryUsageOut,
    InquiryValueAddedOut,
)
from app.inquiry.service import get_customer_account, list_value_added_services
from app.models import Customer
from app.models.inquiry import CustomerAccount

router = APIRouter(prefix="/inquiries", tags=["inquiries"])

DbSession = Annotated[Session, Depends(get_db)]


def _get_account_or_404(db: Session, customer_id: int) -> CustomerAccount:
    account = get_customer_account(db, customer_id)
    if account is None:
        raise HTTPException(status_code=404, detail="未查询到账户信息")
    return account


def _audit_query(db: Session, customer: Customer, action: str, account: CustomerAccount) -> None:
    """查询审计留痕（CONTEXT › 审计日志：查询类调用 + 敏感数据访问均需记录）。"""
    write_audit_log(
        db,
        actor_type="customer",
        actor_id=customer.id,
        action=action,
        detail={"phone": customer.phone, "account_id": account.id},
    )


@router.get("/balance", response_model=InquiryBalanceOut)
def balance(db: DbSession, current: CurrentCustomer) -> dict:
    """话费余额查询（US-3）。"""
    account = _get_account_or_404(db, current.id)
    _audit_query(db, current, "inquiry.balance", account)
    return {"phone": current.phone, "balance": account.balance}


@router.get("/plan", response_model=InquiryPlanOut)
def plan(db: DbSession, current: CurrentCustomer) -> dict:
    """当前套餐详情查询（US-4）。"""
    account = _get_account_or_404(db, current.id)
    _audit_query(db, current, "inquiry.plan", account)
    return {
        "phone": current.phone,
        "plan_name": account.plan_name,
        "plan_price": account.plan_price,
    }


@router.get("/usage", response_model=InquiryUsageOut)
def usage(db: DbSession, current: CurrentCustomer) -> dict:
    """通话/流量使用量查询（US-5）。"""
    account = _get_account_or_404(db, current.id)
    _audit_query(db, current, "inquiry.usage", account)
    return {
        "phone": current.phone,
        "call_used": account.call_used,
        "data_used": account.data_used,
    }


@router.get("/contract", response_model=InquiryContractOut)
def contract(db: DbSession, current: CurrentCustomer) -> dict:
    """合约到期时间查询（US-6）。"""
    account = _get_account_or_404(db, current.id)
    _audit_query(db, current, "inquiry.contract", account)
    return {
        "phone": current.phone,
        "contract_expiry_date": account.contract_expiry_date,
    }


@router.get("/value-added-services", response_model=list[InquiryValueAddedOut])
def value_added_services(db: DbSession, current: CurrentCustomer) -> list:
    """已订购增值业务查询（US-7）。"""
    account = _get_account_or_404(db, current.id)
    _audit_query(db, current, "inquiry.vadd", account)
    return list_value_added_services(db, current.id)
