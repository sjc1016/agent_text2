"""conversation agent_id

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-02

B9 循环6（issue #15 / US-20, US-26）：conversations 增加 agent_id（可空）。
- agent_id 指向 users.id（坐席账号，0002 已建 users 表）
- 含义：handed_off 后坐席接入（take_over）回填；为空 =「待接入」，
  /agents/queues 队列以此判定（US-20）；转回助理（transfer_back）置空恢复（US-26）
- 可空：既有/访客会话无坐席主体，SQLite 加列 nullable 即可
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite 不支持非 batch 模式对已有表 ALTER 加带约束列，须用 copy-and-move 策略
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.add_column(
            sa.Column(
                "agent_id",
                sa.Integer,
                # batch 模式将列内联 FK 提取为独立约束，必须命名
                sa.ForeignKey("users.id", name="fk_conversations_agent_id"),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_column("agent_id")
