"""SQLAlchemy ORM 声明基类。

所有业务模型继承 Base；Alembic env.py 接入 Base.metadata 启用迁移元数据。
PRD 依据：实现决策 › 数据库与迁移（SQLAlchemy 2.0）；ADR 0002。
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有 ORM 模型的声明基类。"""
