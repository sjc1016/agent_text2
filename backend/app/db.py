"""SQLAlchemy 引擎工厂 + SQLite PRAGMA（WAL / foreign_keys）+ 会话依赖。

PRD 依据：实现决策 › 数据库与迁移（SQLite WAL）。WAL 经 connect 事件监听器设置，
一旦设置即持久化于 DB 文件。app 与 Alembic env.py 共用本工厂，确保迁移过程同样
启用 WAL，符合「严格迁移纪律：版本化、可回滚」。

get_db 为 FastAPI 依赖，提供请求级 Session；测试经 dependency_overrides 注入临时 DB。
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def create_engine(url: str, **kwargs: Any) -> sa.Engine:
    """创建引擎；SQLite 自动开启 WAL 与外键约束。"""
    engine = sa.create_engine(url, future=True, **kwargs)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn: Any, _record: Any) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


# 应用默认引擎与会话工厂（URL 经 Settings 注入；测试用 dependency_overrides 覆盖）。
_settings = get_settings()
engine = create_engine(_settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：提供请求级 Session，请求结束自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
