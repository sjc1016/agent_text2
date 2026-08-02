"""inquiry schema（查询类业务能力：客户账户状态 + 增值业务订阅）

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-03

B5（issue #13 验收标准3）：查询类业务能力 schema。
- customer_accounts：与 customers 1:1 的账户当前状态快照
  （话费余额/当前套餐/用量/合约到期，US-3~US-6）
- customer_value_added_services：增值业务订阅子表（一客户多行，US-7）
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "customer_id",
            sa.Integer,
            sa.ForeignKey("customers.id"),
            unique=True,
            nullable=False,
        ),
        sa.Column("balance", sa.Float, nullable=False, server_default="0"),
        sa.Column("plan_name", sa.String, nullable=True),
        sa.Column("plan_price", sa.Float, nullable=True),
        sa.Column("call_used", sa.String, nullable=True),
        sa.Column("data_used", sa.String, nullable=True),
        sa.Column("contract_expiry_date", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table(
        "customer_value_added_services",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "customer_id",
            sa.Integer,
            sa.ForeignKey("customers.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("service_name", sa.String, nullable=False),
        sa.Column("monthly_fee", sa.Float, nullable=True),
        sa.Column("status", sa.String, nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("customer_value_added_services")
    op.drop_table("customer_accounts")
