"""B9 循环10：conversations.agent_id 迁移 upgrade/downgrade 可逆。

验收标准（issue #15）：
  Alembic 迁移（Conversation.agent_id）upgrade/downgrade 可逆
  （PRD 依据：测试决策 › schema 迁移 seam；实现决策 › 数据库与迁移）

复用 B7 迁移可逆性验证模式（test_ticket_migrations.py）：
0005 迁移为 conversations 增加可空 agent_id 列（坐席接入绑定），
downgrade 回 0004 时该列消失。
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


def test_conversation_has_agent_id_after_upgrade(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'conv.db'}"
    command.upgrade(_alembic_config(db_url), "head")

    assert "agent_id" in _table_columns(db_url, "conversations")


def test_conversation_agent_id_reversible_on_downgrade(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'conv.db'}"
    cfg = _alembic_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0004")

    assert "agent_id" not in _table_columns(db_url, "conversations"), (
        "agent_id still exists after downgrade to 0004"
    )
