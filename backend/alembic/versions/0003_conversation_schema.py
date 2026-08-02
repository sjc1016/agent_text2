"""conversation schema

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-02

B2 循环1（issue #7 验收7）：conversations / sessions / messages 三表。
- conversations：会话主体（customer_id 允许 null 供访客；status 状态机当前态）
- sessions：会话片段（归属 conversation，起止时间）
- messages：消息记录（归属 conversation，source 四类，循环3 加约束）

外键依赖：conversations → customers（0002 已建）；sessions/messages → conversations。
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "customer_id",
            sa.Integer,
            sa.ForeignKey("customers.id"),
            nullable=True,
        ),
        sa.Column("status", sa.String, nullable=False, server_default="unauthenticated"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Integer,
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime, nullable=True),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Integer,
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum("user", "assistant", "agent", "system", name="message_source"),
            nullable=False,
        ),
        sa.Column("content", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("sessions")
    op.drop_table("conversations")
