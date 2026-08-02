"""Customer 模型（客户 — 已认证的 User，与号码绑定）。

PRD/CONTEXT 依据：CONTEXT.md › 身份与主体 › Customer；ADR 0004（服务密码认证）。
本切片仅含认证相关字段；套餐/合约等订阅关系由查询类切片（B5）扩展。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(11), unique=True, nullable=False)
    service_password_hash: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
