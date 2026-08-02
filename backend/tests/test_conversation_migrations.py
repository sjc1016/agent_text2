"""B2 循环1：会话 schema 迁移（conversations/sessions/messages）upgrade/downgrade 可逆。

验收标准（issue #7）：
  Alembic 迁移 conversations/sessions/messages upgrade/downgrade 可逆
  （PRD 依据：测试决策 › schema 迁移 seam；实现决策 › 数据库与迁移）

复用 B1 循环1 的 upgrade/downgrade 可逆性验证模式（test_auth_migrations.py）。
表结构由 app.models.conversation 定义，0003 迁移手写（可逆性明确）。
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


def _table_exists(db_url: str, table: str) -> bool:
    engine = sa.create_engine(db_url)
    try:
        return table in sa.inspect(engine).get_table_names()
    finally:
        engine.dispose()


def _table_columns(db_url: str, table: str) -> set[str]:
    engine = sa.create_engine(db_url)
    try:
        return {col["name"] for col in sa.inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


def test_conversation_migration_creates_tables_on_upgrade(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'conv.db'}"
    command.upgrade(_alembic_config(db_url), "head")

    for table in ("conversations", "sessions", "messages"):
        assert _table_exists(db_url, table), f"table {table} missing after upgrade"


def test_conversations_has_core_columns(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'conv.db'}"
    command.upgrade(_alembic_config(db_url), "head")
    cols = _table_columns(db_url, "conversations")
    # 会话核心字段：客户外键（访客未认证时允许 null，CONTEXT › 会话）、状态机当前态、创建时间
    for col in ("id", "customer_id", "status", "created_at"):
        assert col in cols, f"conversations missing column {col}"


def test_sessions_has_core_columns(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'conv.db'}"
    command.upgrade(_alembic_config(db_url), "head")
    cols = _table_columns(db_url, "sessions")
    # 会话片段：归属 Conversation、起止时间（CONTEXT › 会话片段）
    for col in ("id", "conversation_id", "started_at", "ended_at"):
        assert col in cols, f"sessions missing column {col}"


def test_messages_has_core_columns(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'conv.db'}"
    command.upgrade(_alembic_config(db_url), "head")
    cols = _table_columns(db_url, "messages")
    # 消息：归属 Conversation、来源（四类）、内容、创建时间（CONTEXT › 消息）
    for col in ("id", "conversation_id", "source", "content", "created_at"):
        assert col in cols, f"messages missing column {col}"


def test_conversation_migration_reversible_on_downgrade(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'conv.db'}"
    cfg = _alembic_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    for table in ("conversations", "sessions", "messages"):
        assert not _table_exists(db_url, table), (
            f"table {table} still exists after downgrade to base"
        )
