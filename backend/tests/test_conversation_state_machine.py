"""B2 循环6：会话状态机流转（service 层纯逻辑）。

验收标准（issue #7）：
  会话状态机流转（Unauthenticated→Authenticated→In-Progress→Handed-off→Closed）
  推送 conversation.state
  （PRD 依据：实现决策 › 会话状态机；测试决策 › WS 事件 seam；US-18）

PRD line 286 状态机：
  Unauthenticated → Authenticated → In-Progress（等待二次确认）
                                  → Authenticated（Ticket 入队后回退）
                                  → Handed-off（转接）→ Closed

本文件测 service 层 transition_conversation_state 的合法/非法转换与持久化；
WS 推送 conversation.state 在 test_ws_events.py 测。
"""

from __future__ import annotations

import pytest

from app.conversation.service import transition_conversation_state
from app.models import Conversation


def _make_conv(status: str = "unauthenticated", customer_id: int | None = None) -> Conversation:
    return Conversation(customer_id=customer_id, status=status)


def test_transition_unauthenticated_to_authenticated(db):
    conv = _make_conv("unauthenticated")
    db.add(conv)
    db.flush()

    transitioned = transition_conversation_state(db, conv, "authenticated")
    db.commit()

    assert transitioned.status == "authenticated"
    db.refresh(conv)
    assert conv.status == "authenticated"


def test_transition_full_happy_path(db):
    """PRD line 286 正向路径：unauth→auth→in_progress→auth(回退)→handed_off→closed。"""
    conv = _make_conv("unauthenticated")
    db.add(conv)
    db.flush()

    for new_state in ("authenticated", "in_progress", "authenticated", "handed_off", "closed"):
        transition_conversation_state(db, conv, new_state)
    db.commit()

    db.refresh(conv)
    assert conv.status == "closed"


@pytest.mark.parametrize(
    "from_state,new_state",
    [
        ("unauthenticated", "in_progress"),  # 跳过 authenticated
        ("unauthenticated", "handed_off"),  # 跳过 authenticated
        ("authenticated", "unauthenticated"),  # 不可回退到未认证
        ("in_progress", "handed_off"),  # 办理中不可直接转接，需先回退 authenticated
        ("closed", "authenticated"),  # 终态不可再流转
        ("closed", "handed_off"),
    ],
)
def test_transition_rejects_illegal(db, from_state, new_state):
    conv = _make_conv(from_state)
    db.add(conv)
    db.flush()

    with pytest.raises(ValueError):
        transition_conversation_state(db, conv, new_state)

    # 状态不变
    db.refresh(conv)
    assert conv.status == from_state


def test_transition_rejects_unknown_state(db):
    conv = _make_conv("authenticated")
    db.add(conv)
    db.flush()

    with pytest.raises(ValueError):
        transition_conversation_state(db, conv, "frozen")  # 非法状态名


def test_transition_same_state_rejected(db):
    """同态转换无意义，拒绝（避免无操作流转污染事件流）。"""
    conv = _make_conv("authenticated")
    db.add(conv)
    db.flush()

    with pytest.raises(ValueError):
        transition_conversation_state(db, conv, "authenticated")
