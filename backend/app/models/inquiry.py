"""查询类领域模型（Customer 账户状态 + 增值业务订阅）。

PRD 依据：
  - CONTEXT.md › 业务能力 / 查询类：只读操作，Customer 认证后可直接调用，
    返回当前账户状态与历史信息
  - CONTEXT.md › 知识来源：结构化数据（资费表等）
  - 用户故事 US-3~US-7（话费余额 / 当前套餐详情 / 使用量 / 合约到期 / 增值业务）

说明：
  - customer_accounts 与 customers 1:1（一号一户），存账户当前状态快照；
  - customer_value_added_services 为增值业务订阅子表（一客户多行）。
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CustomerAccount(Base):
    """客户账户当前状态（话费余额 / 当前套餐 / 用量 / 合约到期，US-3~US-6）。

    一号一户（CONTEXT › 业务规则）：customer_id 唯一，一客户一条。
    """

    __tablename__ = "customer_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"), unique=True, nullable=False
    )
    balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # 话费余额（元）
    plan_name: Mapped[str | None] = mapped_column(String, nullable=True)  # 当前套餐名
    plan_price: Mapped[float | None] = mapped_column(Float, nullable=True)  # 套餐月费（元）
    call_used: Mapped[str | None] = mapped_column(String, nullable=True)  # 通话使用量
    data_used: Mapped[str | None] = mapped_column(String, nullable=True)  # 流量使用量
    contract_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # 合约到期日
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CustomerValueAddedService(Base):
    """客户已订购增值业务（US-7）：一客户可多行。"""

    __tablename__ = "customer_value_added_services"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    service_name: Mapped[str] = mapped_column(String, nullable=False)  # 增值业务名
    monthly_fee: Mapped[float | None] = mapped_column(Float, nullable=True)  # 月费（元）
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")  # active/inactive
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
