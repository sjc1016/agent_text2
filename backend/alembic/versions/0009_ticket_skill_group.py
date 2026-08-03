"""tickets skill_group

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-03

B8（issue #17 验收5 / CONTEXT › 离线兜底）：tickets 增加 skill_group（可空）。
- 含义：回呼请求 Ticket（离线兜底创建）派单目标技能组
  （套餐业务组/故障报修组/投诉处理组，CONTEXT › 技能组）
- 可空：既有/普通工单无技能组目标，SQLite 加列 nullable 即可
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.add_column(sa.Column("skill_group", sa.String, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tickets") as batch_op:
        batch_op.drop_column("skill_group")
