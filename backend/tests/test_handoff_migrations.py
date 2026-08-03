"""B8 循环5：tickets.skill_group 迁移 upgrade/downgrade 可逆。

验收标准（issue #17 / PRD 测试决策 › schema 迁移 seam）：
  每个含 schema 变更的 PR 必须带可回滚迁移脚本；
  0009 迁移 upgrade 加列、downgrade 回退到 0008（仅移除本列，保留 tickets 表）。

表结构由 app.models 定义，0009 迁移手写（可逆性明确），env.py 接入 Base.metadata。
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


def _table_columns(db_url: str, table: str) -> set[str]:
    engine = sa.create_engine(db_url)
    try:
        return {col["name"] for col in sa.inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


def test_upgrade_adds_skill_group_column(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'handoff.db'}"
    command.upgrade(_alembic_config(db_url), "head")
    cols = _table_columns(db_url, "tickets")
    assert "skill_group" in cols


def test_downgrade_to_0008_removes_skill_group_but_keeps_tickets(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'handoff.db'}"
    cfg = _alembic_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0008")
    cols = _table_columns(db_url, "tickets")
    assert "skill_group" not in cols
    # tickets 表本体保留（仅回退本列）
    engine = sa.create_engine(db_url)
    try:
        assert "tickets" in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_upgrade_after_downgrade_reapplies_column(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'handoff.db'}"
    cfg = _alembic_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0008")
    command.upgrade(cfg, "head")
    cols = _table_columns(db_url, "tickets")
    assert "skill_group" in cols
