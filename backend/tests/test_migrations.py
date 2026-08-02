"""F0 循环3：Alembic baseline 迁移 upgrade/downgrade 可逆 + SQLite WAL。

PRD 依据：实现决策 › 数据库与迁移；测试决策 › schema 迁移 seam。
通过 Alembic 公共 API（command.upgrade/downgrade）+ SQLAlchemy 检查验证：
  1. upgrade head 后迁移已应用（alembic_version 记录当前 revision）
  2. SQLite WAL 已启用（PRAGMA journal_mode = wal）
  3. downgrade base 后迁移已回滚（无 revision 记录）

本测试构成 PRD「测试决策 › schema 迁移 seam」：后续 B-slice 增量迁移（含向量库
schema）复用同一 upgrade/downgrade 可逆性验证模式。
"""

from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config

from alembic import command

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "backend" / "alembic.ini"


def _alembic_config(db_url: str) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _current_revision(db_url: str):
    engine = sa.create_engine(db_url)
    try:
        insp = sa.inspect(engine)
        if "alembic_version" not in insp.get_table_names():
            return None
        with engine.connect() as conn:
            return conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
    finally:
        engine.dispose()


def _journal_mode(db_url: str) -> str | None:
    engine = sa.create_engine(db_url)
    try:
        with engine.connect() as conn:
            return conn.exec_driver_sql("PRAGMA journal_mode").scalar()
    finally:
        engine.dispose()


def test_alembic_upgrade_downgrade_reversible_and_wal(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    cfg = _alembic_config(db_url)

    command.upgrade(cfg, "head")
    assert _current_revision(db_url) is not None, "upgrade did not apply a revision"
    assert _journal_mode(db_url) == "wal", "SQLite WAL not enabled"

    command.downgrade(cfg, "base")
    assert _current_revision(db_url) is None, "downgrade did not reverse to base"
