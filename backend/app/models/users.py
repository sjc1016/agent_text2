"""User 模型（坐席账号 — agent-console 登录主体）。

PRD/CONTEXT 依据：CONTEXT.md › 角色与系统 › 坐席；US-19/US-30。
本切片仅建表（坐席登录与状态切换由 B9 实现）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="offline")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
