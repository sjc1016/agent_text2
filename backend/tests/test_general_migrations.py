"""B4 循环5：通用咨询 schema 迁移（RAG 知识库 + 结构化参考数据）upgrade/downgrade 可逆。

验收标准（issue #12）：
  sqlite-vec 向量库 schema 经 Alembic 迁移管理，upgrade/downgrade 可逆
  （PRD 依据：实现决策 › 数据库与迁移；测试决策 › schema 迁移 seam）

复用 B1/B2 的 upgrade/downgrade 可逆性验证模式（test_auth_migrations.py）。
表结构由 app.models.general 定义；knowledge_vec 为 sqlite-vec vec0 虚拟表，
不经 SQLAlchemy metadata，迁移 0006 手写 DDL（可逆性明确）。
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


def test_general_migration_creates_tables_on_upgrade(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'general.db'}"
    command.upgrade(_alembic_config(db_url), "head")

    for table in (
        "knowledge_documents",
        "plans",
        "coverage_areas",
        "business_halls",
        "knowledge_vec",  # sqlite-vec vec0 虚拟表（不经 metadata，迁移显式创建）
    ):
        assert _table_exists(db_url, table), f"table {table} missing after upgrade"


def test_knowledge_documents_has_core_columns(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'general.db'}"
    command.upgrade(_alembic_config(db_url), "head")
    cols = _table_columns(db_url, "knowledge_documents")
    # 知识文档：分类（policy/rule/manual）、标题、正文、创建时间（CONTEXT › 知识来源）
    for col in ("id", "category", "title", "content", "created_at"):
        assert col in cols, f"knowledge_documents missing column {col}"


def test_structured_tables_have_core_columns(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'general.db'}"
    command.upgrade(_alembic_config(db_url), "head")

    # 套餐目录 / 资费表（US-1）
    plan_cols = _table_columns(db_url, "plans")
    for col in ("id", "name", "price", "data_allowance", "call_minutes"):
        assert col in plan_cols, f"plans missing column {col}"

    # 网络覆盖（US-1）
    cov_cols = _table_columns(db_url, "coverage_areas")
    for col in ("id", "area", "network_type", "level"):
        assert col in cov_cols, f"coverage_areas missing column {col}"

    # 营业厅列表（US-1）
    hall_cols = _table_columns(db_url, "business_halls")
    for col in ("id", "name", "district", "address"):
        assert col in hall_cols, f"business_halls missing column {col}"


def test_general_migration_reversible_on_downgrade(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'general.db'}"
    cfg = _alembic_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    for table in (
        "knowledge_documents",
        "plans",
        "coverage_areas",
        "business_halls",
        "knowledge_vec",
    ):
        assert not _table_exists(db_url, table), (
            f"table {table} still exists after downgrade to base"
        )
