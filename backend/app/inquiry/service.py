"""B5 查询类业务能力服务（深模块：只读数据访问，隐藏 ORM 细节）。

PRD 依据：
  - 实现决策 › API 契约（/inquiries/* 查询类业务能力）
  - 测试决策 › tool 调用 seam（查询类业务能力返回正确数据）
  - CONTEXT.md › 业务能力 / 查询类（只读，Customer 认证后可直接调用）

设计说明（深模块）：
  - 对外接口小：get_customer_account / list_value_added_services；
  - 内部封装：按 customer_id 定位账户快照与增值订阅；
  - 纯查询无副作用（审计由调用方：REST 路由 / tool audit_hook 负责）。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.inquiry import CustomerAccount, CustomerValueAddedService


def get_customer_account(db: Session, customer_id: int) -> CustomerAccount | None:
    """按客户返回账户当前状态快照；无记录返回 None（不编造）。"""
    return db.execute(
        sa.select(CustomerAccount).where(CustomerAccount.customer_id == customer_id)
    ).scalar_one_or_none()


def list_value_added_services(db: Session, customer_id: int) -> list[CustomerValueAddedService]:
    """按客户返回已订购增值业务列表（US-7）。"""
    return list(
        db.execute(
            sa.select(CustomerValueAddedService)
            .where(CustomerValueAddedService.customer_id == customer_id)
            .order_by(CustomerValueAddedService.id)
        )
        .scalars()
        .all()
    )
