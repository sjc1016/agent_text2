"""general-info schema（通用咨询：RAG 知识库 + 结构化参考数据）

Revision ID: 0006
Revises: 0003
Create Date: 2026-08-03

B4（issue #12 验收标准4）：通用咨询类业务能力 schema。
- knowledge_documents：非结构化知识文档（政策/规则/手册），向量存于 knowledge_vec
- knowledge_vec：sqlite-vec vec0 虚拟表（rowid ↔ knowledge_documents.id），
  维度 256（EMBEDDING_DIM），不经 SQLAlchemy metadata（create_all 不覆盖）
- plans / coverage_areas / business_halls：结构化参考数据（套餐目录/覆盖/营业厅）

向量表 DDL 内联于此（不可随 embedding 实现漂移）；运行时建表 SQL 与
测试 fixture 共用 app.general.service.CREATE_VEC_TABLE_SQL（维度假定一致，
若修改 EMBEDDING_DIM 须同步迁移并重建索引）。

依赖 sqlite-vec 扩展：env.py 经 app.db.create_engine 加载（connect 事件监听器）。
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("category", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("content", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("data_allowance", sa.String, nullable=True),
        sa.Column("call_minutes", sa.String, nullable=True),
        sa.Column("description", sa.String, nullable=True),
    )
    op.create_table(
        "coverage_areas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("area", sa.String, nullable=False),
        sa.Column("network_type", sa.String, nullable=False),
        sa.Column("level", sa.String, nullable=False),
    )
    op.create_table(
        "business_halls",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("district", sa.String, nullable=False),
        sa.Column("address", sa.String, nullable=False),
        sa.Column("phone", sa.String, nullable=True),
        sa.Column("business_hours", sa.String, nullable=True),
    )
    # sqlite-vec vec0 虚拟表（向量检索；downgrade 可逆）
    op.execute("CREATE VIRTUAL TABLE knowledge_vec USING vec0(embedding float[256])")


def downgrade() -> None:
    op.execute("DROP TABLE knowledge_vec")
    op.drop_table("business_halls")
    op.drop_table("coverage_areas")
    op.drop_table("plans")
    op.drop_table("knowledge_documents")
