"""客户侧请求/响应 schema（Pydantic）。

PRD 依据：实现决策 › API 契约 /customers/me（OpenAPI 自动生成）；用户故事 US-17。
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class CustomerProfileOut(BaseModel):
    """当前客户资料 + 账户信息（/customers/me 响应，US-17）。

    客户视角读取自身账户：号码不脱敏（与 B12 坐席侧 /agents/customers/{id}
    脱敏视图不同——自己看自己）；authenticated 恒真故省略；账户字段复用
    inquiry 数据源 CustomerAccount（余额/套餐名/合约到期），与坐席侧同一数据源。
    """

    id: int
    phone: str
    name: str | None
    balance: float
    plan_name: str | None
    contract_expiry_date: date | None
