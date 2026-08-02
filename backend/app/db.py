"""SQLAlchemy 引擎工厂 + SQLite PRAGMA（WAL / foreign_keys）。

PRD 依据：实现决策 › 数据库与迁移（SQLite WAL）。WAL 经 connect 事件监听器设置，
一旦设置即持久化于 DB 文件。app 与 Alembic env.py 共用本工厂，确保迁移过程同样
启用 WAL，符合「严格迁移纪律：版本化、可回滚」。
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy import event


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
