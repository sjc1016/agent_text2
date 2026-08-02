"""OpenAPI schema 同步校验/导出。

F0 循环6（issue #2 / PRD › API 文档：OpenAPI 自动生成）：
  FastAPI OpenAPI schema 的 SSOT 是 app.openapi()，committed 副本为
  backend/openapi.json。CI 跑 `--check` 守卫漂移；本地用 `--write` 更新。

用法：
    python scripts/openapi_sync.py --check   # CI 门禁：不一致退出 1
    python scripts/openapi_sync.py --write   # 本地：导出并写入 committed 副本
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 脚本位于 scripts/，需将 backend/ 纳入 import 搜索路径以 import app.main。
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.main import app  # noqa: E402

OPENAPI_PATH = REPO_ROOT / "backend" / "openapi.json"


def current_schema() -> dict[str, object]:
    return app.openapi()


def write() -> None:
    schema = current_schema()
    OPENAPI_PATH.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {OPENAPI_PATH.relative_to(REPO_ROOT)}")


def check() -> int:
    if not OPENAPI_PATH.is_file():
        print(
            f"FAIL: {OPENAPI_PATH.relative_to(REPO_ROOT)} 不存在，"
            "先运行 `python scripts/openapi_sync.py --write` 生成",
            file=sys.stderr,
        )
        return 1
    committed = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    if committed != current_schema():
        print(
            "FAIL: OpenAPI schema 漂移，运行 `python scripts/openapi_sync.py --write` 更新",
            file=sys.stderr,
        )
        return 1
    print("OK: OpenAPI schema 同步（app.openapi() ↔ backend/openapi.json）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenAPI schema 同步校验/导出")
    parser.add_argument("--write", action="store_true", help="导出并写入 committed openapi.json")
    parser.add_argument(
        "--check", action="store_true", help="校验一致性（默认行为，CI 门禁）"
    )
    args = parser.parse_args()
    if args.write:
        write()
        return 0
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
