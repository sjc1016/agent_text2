"""CI 门禁脚本：校验 WS 事件契约双边一致。

F0 循环5（issue #2 / PRD 第282行）：
  供 CI 流水线调用，校验 frontend/shared/events.ts 与 backend/app/ws/events.py
  事件名集合逐字一致。一致退出 0，漂移退出 1 并打印差异。

用法（从仓库根）：
    python scripts/check_ws_events.py
"""

import sys
from pathlib import Path

# 脚本位于 scripts/，需将 backend/ 纳入 import 搜索路径以复用 app.ws.contract。
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.ws.contract import assert_events_consistent  # noqa: E402

TS_EVENTS_PATH = REPO_ROOT / "frontend" / "shared" / "src" / "events.ts"


def main() -> int:
    try:
        assert_events_consistent(TS_EVENTS_PATH)
    except (AssertionError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("OK: WS 事件名双边一致（frontend/shared/events.ts ↔ backend/app/ws/events.py）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
