"""客户侧只读端点（issue #53 B13）。

  GET /customers/me — 当前客户资料 + 账户信息（US-17 账号信息）
  GET /notifications — 当前客户站内通知列表（US-14 通知预览条数据源）

鉴权复用 B1 的 CurrentCustomer（Authorization header Bearer，未认证 401）。
账户数据源复用 B12 的 get_customer_profile（同一 CustomerAccount 快照，
坐席侧 /agents/customers/{id} 同源）；无账户记录 → 404（不编造）。
PRD 依据：实现决策 › API 契约（RESTful 端点）；测试决策 › HTTP 集成 seam；
用户故事 US-14 / US-17。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agents.service import get_customer_profile
from app.auth.dependencies import CurrentCustomer
from app.customers.schemas import CustomerMeOut, NotificationOut
from app.customers.service import list_customer_notifications
from app.db import get_db
from app.models import Notification

router = APIRouter(tags=["customer"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/customers/me", response_model=CustomerMeOut)
def read_current_customer_me(current: CurrentCustomer, db: DbSession) -> CustomerMeOut:
    """当前客户账户资料（未认证 401 由 CurrentCustomer 守卫）。

    复用 B12 同一数据源 get_customer_profile（Customer + CustomerAccount）；
    Customer 或账户任一缺失 → 404（与坐席侧同语义，不编造账户信息）。
    """
    profile = get_customer_profile(db, current.id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账户信息不存在")
    customer, account = profile
    return CustomerMeOut(
        id=customer.id,
        phone=customer.phone,
        name=customer.name,
        balance=account.balance,
        plan_name=account.plan_name,
        contract_expiry_date=account.contract_expiry_date,
    )


@router.get("/notifications", response_model=list[NotificationOut])
def read_current_customer_notifications(
    current: CurrentCustomer, db: DbSession
) -> list[Notification]:
    """当前客户站内通知列表（按时间倒序，含未读标记；未认证 401）。

    US-14 通知预览条数据源（页面打开前产生的通知经本端点可获取，
    与 WS notification.push 实时推送互补）。response_model 负责 ORM 序列化。
    """
    return list_customer_notifications(db, current.id)
