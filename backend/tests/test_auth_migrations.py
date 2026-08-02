"""B1 循环1：认证 schema 迁移（customers/users/audit_logs）upgrade/downgrade 可逆。

验收标准（issue #4）：
  Alembic 迁移 customers/users/audit_logs upgrade/downgrade 可逆
  （PRD 依据：测试决策 › schema 迁移 seam；实现决策 › 数据库与迁移）

复用 F0 循环3 的 upgrade/downgrade 可逆性验证模式（test_migrations.py）。
表结构由 app.models 定义，0002 迁移手写（可逆性明确），env.py 接入 Base.metadata。
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


def test_auth_migration_creates_tables_on_upgrade(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'auth.db'}"
    command.upgrade(_alembic_config(db_url), "head")

    for table in ("customers", "users", "audit_logs"):
        assert _table_exists(db_url, table), f"table {table} missing after upgrade"


def test_customers_has_auth_columns(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'auth.db'}"
    command.upgrade(_alembic_config(db_url), "head")
    cols = _table_columns(db_url, "customers")
    # 认证关键字段：手机号（唯一）+ 服务密码 hash（bcrypt 成本 12）
    for col in ("phone", "service_password_hash"):
        assert col in cols, f"customers missing column {col}"


def test_users_has_agent_account_columns(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'auth.db'}"
    command.upgrade(_alembic_config(db_url), "head")
    cols = _table_columns(db_url, "users")
    # 坐席账号字段（坐席登录 B9 用，本切片仅建表）
    for col in ("employee_id", "password_hash"):
        assert col in cols, f"users missing column {col}"


def test_audit_logs_has_audit_columns(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'auth.db'}"
    command.upgrade(_alembic_config(db_url), "head")
    cols = _table_columns(db_url, "audit_logs")
    # 审计日志字段（CONTEXT.md › 审计日志：操作主体/动作/详情/时间）
    for col in ("actor_type", "action", "created_at"):
        assert col in cols, f"audit_logs missing column {col}"


def test_auth_migration_reversible_on_downgrade(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'auth.db'}"
    cfg = _alembic_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    for table in ("customers", "users", "audit_logs"):
        assert not _table_exists(db_url, table), (
            f"table {table} still exists after downgrade to base"
        )
