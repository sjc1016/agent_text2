"""baseline

Revision ID: 0001
Revises:
Create Date: 2026-08-02

F0 循环3 baseline：建立迁移起点。业务 schema 由 B-slice 迁移增量加入，
每条迁移须可逆（upgrade/downgrade），复用同一 schema 迁移 seam 验证。
"""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # baseline：迁移起点，无业务 schema 变更。
    pass


def downgrade() -> None:
    pass
