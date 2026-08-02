"""查询类业务能力请求/响应 schema（Pydantic）。

PRD 依据：实现决策 › API 契约（/inquiries/* 查询类业务能力，OpenAPI 自动生成）。
查询类为只读，无请求体；响应直接描述账户当前状态（US-3~US-7）。
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class InquiryBalanceOut(BaseModel):
    """话费余额（US-3）。"""

    phone: str
    balance: float


class InquiryPlanOut(BaseModel):
    """当前套餐详情（US-4）。"""

    phone: str
    plan_name: str | None
    plan_price: float | None


class InquiryUsageOut(BaseModel):
    """通话/流量使用量（US-5）。"""

    phone: str
    call_used: str | None
    data_used: str | None


class InquiryContractOut(BaseModel):
    """合约到期时间（US-6）。"""

    phone: str
    contract_expiry_date: date | None


class InquiryValueAddedOut(BaseModel):
    """已订购增值业务（US-7）。"""

    model_config = ConfigDict(from_attributes=True)

    service_name: str
    monthly_fee: float | None
    status: str
