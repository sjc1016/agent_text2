"""B11 循环1（issue #42）：conversations.handoff_reason 迁移 upgrade/downgrade 可逆。

验收标准（issue #42 AC1）：
  Alembic 迁移新增 conversations.handoff_reason（可回滚）
  （PRD 依据：实现决策 › 转接触发；测试决策 › schema 迁移 seam）

复用 B9 迁移可逆性验证模式（test_conversation_agent_migration.py）：
0010 迁移为 conversations 增加可空 handoff_reason 列（转接原因持久化，
Queue 页展示来源），downgrade 回 0009 时该列消失。
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


def test_conversation_has_handoff_reason_after_upgrade(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'conv.db'}"
    command.upgrade(_alembic_config(db_url), "head")

    assert "handoff_reason" in _table_columns(db_url, "conversations")


def test_conversation_handoff_reason_reversible_on_downgrade(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'conv.db'}"
    cfg = _alembic_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0009")

    assert "handoff_reason" not in _table_columns(db_url, "conversations"), (
        "handoff_reason still exists after downgrade to 0009"
    )
