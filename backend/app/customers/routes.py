"""客户侧 REST 路由（/customers/me）。

B13（issue #53 AC1，US-17）：客户读取自身账户资料——「我的」页账号卡片
套餐简述的真实数据源，替换 UI-C-5（#11）的 mock-先行数据。

鉴权复用 B1 的 CurrentCustomer（Authorization header Bearer）。
账户数据源复用 B12 /agents/customers/{id} 同一查询（Customer + CustomerAccount，
后端唯一账户快照来源）；Customer 存在但无账户 → 404（不编造，与坐席侧一致）。
PRD 依据：实现决策 › API 契约 /customers/me；测试决策 › HTTP 集成 seam；
          用户故事 US-17。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agents.service import get_customer_profile
from app.auth.dependencies import CurrentCustomer
from app.customers.schemas import CustomerProfileOut
from app.db import get_db

router = APIRouter(prefix="/customers", tags=["customer"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/me", response_model=CustomerProfileOut)
def read_my_profile(db: DbSession, current: CurrentCustomer) -> CustomerProfileOut:
    """返回当前认证客户的资料 + 账户信息（US-17，账号卡片数据源）。

    仅当前客户自身可读（CurrentCustomer 守卫）；Customer 存在但无账户记录
    → 404（不编造账户信息，与 B12 坐席侧行为一致）。
    """
    profile = get_customer_profile(db, current.id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未查询到账户信息")
    customer, account = profile
    return CustomerProfileOut(
        id=customer.id,
        phone=customer.phone,
        name=customer.name,
        balance=account.balance,
        plan_name=account.plan_name,
        contract_expiry_date=account.contract_expiry_date,
    )
