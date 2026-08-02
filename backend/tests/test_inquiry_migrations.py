"""B5 查询类 schema 迁移（客户账户状态 + 增值业务订阅）upgrade/downgrade 可逆。

验收标准（issue #13）：
  schema 变更经 Alembic 迁移管理，upgrade/downgrade 可逆
  （PRD 依据：实现决策 › 数据库与迁移；测试决策 › schema 迁移 seam）

复用 B1/B2/B4 的 upgrade/downgrade 可逆性验证模式（test_general_migrations.py）。
表结构由 app.models.inquiry 定义。
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


def test_inquiry_migration_creates_tables_on_upgrade(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'inquiry.db'}"
    command.upgrade(_alembic_config(db_url), "head")

    for table in ("customer_accounts", "customer_value_added_services"):
        assert _table_exists(db_url, table), f"table {table} missing after upgrade"


def test_customer_accounts_has_core_columns(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'inquiry.db'}"
    command.upgrade(_alembic_config(db_url), "head")
    cols = _table_columns(db_url, "customer_accounts")
    # 账户状态快照：余额/套餐/用量/合约到期（US-3~US-6），1:1 客户
    for col in (
        "id",
        "customer_id",
        "balance",
        "plan_name",
        "plan_price",
        "call_used",
        "data_used",
        "contract_expiry_date",
    ):
        assert col in cols, f"customer_accounts missing column {col}"


def test_value_added_services_has_core_columns(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'inquiry.db'}"
    command.upgrade(_alembic_config(db_url), "head")
    cols = _table_columns(db_url, "customer_value_added_services")
    # 增值业务订阅（US-7）：业务名/月费/状态，一客户多行
    for col in ("id", "customer_id", "service_name", "monthly_fee", "status"):
        assert col in cols, f"customer_value_added_services missing column {col}"


def test_inquiry_migration_reversible_on_downgrade(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'inquiry.db'}"
    cfg = _alembic_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    for table in ("customer_accounts", "customer_value_added_services"):
        assert not _table_exists(db_url, table), (
            f"table {table} still exists after downgrade to base"
        )
