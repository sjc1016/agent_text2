"""conversation handoff_reason

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-03

B11（issue #42 AC1 / PRD 实现决策 › 转接触发）：conversations 增加 handoff_reason（可空）。
- 含义：Handoff 触发原因（HandoffReason.value：out_of_scope / transaction_failure /
  explicit_request / negative_sentiment / intent_loop / compliance_risk），
  GET /agents/queues 队列项「转接原因」展示来源（PRD queue 页 UI 设计描述）。
- 持久化方：trigger_handoff 在正常转接与离线兜底两条路径均写入。
- 可空：既有/未转接会话无转接原因，SQLite 加列 nullable 即可。
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite 不支持非 batch 模式对已有表 ALTER 加列，须用 copy-and-move 策略
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.add_column(sa.Column("handoff_reason", sa.String, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_column("handoff_reason")
