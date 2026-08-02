"""Alembic 迁移可逆性校验。

F0 循环6（issue #2 / PRD › 数据库与迁移：严格迁移纪律，版本化、可回滚）：
  CI 跑本脚本验证 upgrade head → downgrade base → upgrade head 完整可逆，
  守卫后续 B-slice 增量迁移（含向量库 schema）不破坏回滚能力。

用法：
    python scripts/check_alembic.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config

REPO_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = REPO_ROOT / "backend" / "alembic.ini"


def check() -> int:
    # Windows 下 SQLite WAL 连接池可能暂留文件句柄，清理时忽略残留错误
    # （CI 在 Linux 无此问题；残留临时文件由 OS 清理 Temp 目录回收）。
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_url = f"sqlite:///{Path(tmp) / 'alembic_check.db'}"
        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")
    print("OK: Alembic 迁移 upgrade head → downgrade base → upgrade head 可逆")
    return 0


if __name__ == "__main__":
    raise SystemExit(check())
