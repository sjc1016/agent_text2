"""WS 事件契约双边一致性校验逻辑。

F0 循环5（issue #2 / PRD 第282行）：
  被 tests/test_ws_event_contract.py 与 scripts/check_ws_events.py 复用，
  守卫 frontend/shared/events.ts 与 backend/app/ws/events.py 事件名集合不漂移。

校验策略：
  - Python 侧事件名来自 app.ws.events.EVENT_NAMES（枚举派生）。
  - TS 侧事件名从 events.ts 文本中正则提取 WS_EVENT_NAMES = [...] as const
    数组内的字符串字面量（单/双引号兼容）。
  - 双边集合必须逐字相等，否则抛带差异详情的 AssertionError。
"""

from __future__ import annotations

import re
from pathlib import Path

from app.ws.events import EVENT_NAMES

_TS_ARRAY_RE = re.compile(
    r"WS_EVENT_NAMES\s*=\s*\[(?P<body>.*?)\]\s*as\s*const",
    re.DOTALL,
)
_TS_STRING_RE = re.compile(r"""['"]([^'"]+)['"]""")


def py_event_names() -> set[str]:
    """后端侧 WS 事件名集合（由 WsEventName 枚举派生）。"""
    return set(EVENT_NAMES)


def extract_ts_event_names(ts_source: str) -> set[str]:
    """从 events.ts 源码提取 WS_EVENT_NAMES 数组中的事件名集合。

    定位 `WS_EVENT_NAMES = [ ... ] as const` 数组块，提取其中所有引号字符串字面量。
    若无法定位数组，抛 ValueError。
    """
    match = _TS_ARRAY_RE.search(ts_source)
    if not match:
        raise ValueError("无法在 events.ts 中定位 WS_EVENT_NAMES = [...] as const 数组")
    return set(_TS_STRING_RE.findall(match.group("body")))


def assert_events_consistent(ts_path: Path | str) -> None:
    """断言 TS 侧与 Python 侧 WS 事件名集合逐字一致，不一致抛 AssertionError。

    报错信息包含仅 TS 有 / 仅 Python 有 的差异，便于定位漂移。
    """
    ts_source = Path(ts_path).read_text(encoding="utf-8")
    ts_names = extract_ts_event_names(ts_source)
    py_names = py_event_names()

    if ts_names != py_names:
        only_ts = sorted(ts_names - py_names)
        only_py = sorted(py_names - ts_names)
        raise AssertionError(f"WS 事件名双边不一致：仅 TS 有 {only_ts}；仅 Python 有 {only_py}")
