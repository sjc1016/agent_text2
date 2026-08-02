"""ticket schema

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-02

B7 循环1/9（issue #10）：tickets / notifications 两表。
- tickets：统一 Ticket 模型（PRD line 288-292；CONTEXT › 工单状态机）
  - customer_id 允许 null（Visitor 创建时），仅记录联系方式 contact_name+contact_phone
  - status 两状态机状态并集（办理类/工单类由 service 层按 ticket_type 路由）
- notifications：站内通知（CONTEXT › 通知；UI-C-4 通知预览条数据源）

外键依赖：tickets → conversations（0003 已建）/ customers（0002 已建）；
notifications → tickets / customers。
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Integer,
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column(
            "ticket_type",
            sa.Enum("transaction", "ticketing", name="ticket_type"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "processing",
                "effective",
                "failed",
                "dispatched",
                "in_progress",
                "awaiting_confirmation",
                "closed",
                "cancelled",
                name="ticket_status",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("content", sa.String, nullable=False),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("contact_name", sa.String, nullable=True),
        sa.Column("contact_phone", sa.String, nullable=True),
        sa.Column("creator_type", sa.String, nullable=False),
        sa.Column("creator_id", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "ticket_id",
            sa.Integer,
            sa.ForeignKey("tickets.id"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            sa.Integer,
            sa.ForeignKey("customers.id"),
            nullable=True,
        ),
        sa.Column("message", sa.String, nullable=False),
        sa.Column("read", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("tickets")
