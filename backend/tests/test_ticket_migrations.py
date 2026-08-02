"""B7 循环9：tickets/notifications schema 迁移 upgrade/downgrade 可逆。

验收标准（issue #10）：
  Alembic 迁移 tickets upgrade/downgrade 可逆
  （PRD 依据：测试决策 › schema 迁移 seam；实现决策 › 数据库与迁移）

复用 F0/B1 的升级可逆性验证模式（test_migrations.py / test_auth_migrations.py）。
表结构由 app.models 定义，0004 迁移手写（可逆性明确），env.py 接入 Base.metadata。
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


def test_ticket_migration_creates_tables_on_upgrade(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'ticket.db'}"
    command.upgrade(_alembic_config(db_url), "head")

    for table in ("tickets", "notifications"):
        assert _table_exists(db_url, table), f"table {table} missing after upgrade"


def test_tickets_has_ticket_columns(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'ticket.db'}"
    command.upgrade(_alembic_config(db_url), "head")
    cols = _table_columns(db_url, "tickets")
    # 统一 Ticket 模型（PRD line 288-292：Conversation 关联、类型、状态、Customer 可空）
    for col in (
        "conversation_id",
        "ticket_type",
        "status",
        "content",
        "customer_id",
        "contact_name",
        "contact_phone",
        "creator_type",
    ):
        assert col in cols, f"tickets missing column {col}"


def test_notifications_has_notification_columns(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'ticket.db'}"
    command.upgrade(_alembic_config(db_url), "head")
    cols = _table_columns(db_url, "notifications")
    # 站内通知（CONTEXT › 通知：Ticket 状态变化的站内消息）
    for col in ("ticket_id", "message", "read"):
        assert col in cols, f"notifications missing column {col}"


def test_ticket_migration_reversible_on_downgrade(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'ticket.db'}"
    cfg = _alembic_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    for table in ("tickets", "notifications"):
        assert not _table_exists(db_url, table), (
            f"table {table} still exists after downgrade to base"
        )
