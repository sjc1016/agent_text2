"""合并迁移：线性化 B7/B9（0004/0005）与 B4（0006）两个迁移头。

B7/B9（issue #10/#15，PR #32）与 B4（issue #12，PR #33）在独立分支上并行开发，
各自按预留编号提交迁移：B7=ticket 0004、B9=agent 0005、B4=general 0006。
二者均以 0003（conversation schema）为父，导致合并后出现双头，需合并迁移收敛。

本迁移无 schema 变更（两分支 schema 互不重叠），仅收敛 Alembic revision 图。
"""

from __future__ import annotations

revision = "0007"
down_revision = ("0005", "0006")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """无操作：0004/0005 与 0006 的 schema 相互独立，无需变更。"""
    pass


def downgrade() -> None:
    """无操作：与 upgrade 对称，保持可逆。"""
    pass
