"""F0 循环5：WS 事件契约双边一致性校验。

验收标准（issue #2 / PRD 第282行）：
  frontend/shared/events.ts 与 backend/app/ws/events.py 事件名集合逐字一致，
  CI 通过 scripts/check_ws_events.py 调用同一校验逻辑守卫漂移。

本测试驱动 app.ws.contract 校验逻辑：
  - TS 源解析能正确提取 WS_EVENT_NAMES 数组中的事件名；
  - 真实 events.ts 与 events.py 双边一致；
  - 当 TS 侧缺失事件时，校验能检出并抛出带差异详情的 AssertionError。
"""

from pathlib import Path

import pytest

from app.ws.contract import (
    assert_events_consistent,
    extract_ts_event_names,
    py_event_names,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TS_EVENTS_PATH = REPO_ROOT / "frontend" / "shared" / "src" / "events.ts"


def test_extract_ts_event_names_parses_single_and_double_quotes():
    source = """
    export const WS_EVENT_NAMES = [
      'llm.token',
      "message.new",
    ] as const
    """
    assert extract_ts_event_names(source) == {"llm.token", "message.new"}


def test_extract_ts_event_names_raises_when_array_absent():
    with pytest.raises(ValueError):
        extract_ts_event_names("export const X = 1;")


def test_py_event_names_matches_event_names_constant():
    from app.ws.events import EVENT_NAMES

    assert py_event_names() == set(EVENT_NAMES)


def test_real_events_ts_and_py_are_consistent():
    """真实双边文件事件名集合必须逐字一致（CI 守卫的核心断言）。"""
    assert_events_consistent(TS_EVENTS_PATH)


def test_assert_consistent_detects_missing_event(tmp_path):
    """TS 侧缺失事件时，校验必须抛 AssertionError 并反映差异。"""
    missing_source = """
    export const WS_EVENT_NAMES = [
      'llm.token',
    ] as const
    """
    tmp_ts = tmp_path / "events.ts"
    tmp_ts.write_text(missing_source, encoding="utf-8")

    with pytest.raises(AssertionError):
        assert_events_consistent(tmp_ts)
