"""B11 循环2（issue #42 AC1）：trigger_handoff 持久化转接原因到会话。

验收标准（issue #42 AC1）：
  trigger_handoff 正常转接与离线兜底均持久化转接原因
  （PRD 依据：实现决策 › 转接触发；测试决策 › schema 迁移 seam）

行为（PRD queue 页 UI 设计描述）：队列每行显示转接原因（Caption），数据源为
Conversation.handoff_reason —— 触发 Handoff 时（正常转接 / 离线兜底两条路径）
均把 HandoffReason.value 写入会话，供 GET /agents/queues 读取。
"""

from datetime import datetime

import bcrypt

from app.handoff.service import trigger_handoff
from app.handoff.triggers import HandoffReason

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_customer(db, phone: str = "13800000111"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password("x"))
    db.add(customer)
    db.commit()
    return customer


def _create_conversation(db, customer_id: int, status: str = "authenticated"):
    from app.models import Conversation

    conv = Conversation(customer_id=customer_id, status=status)
    db.add(conv)
    db.commit()
    return conv


def _create_agent(db, status: str = "online"):
    from app.models import User

    agent = User(
        employee_id="A7001",
        password_hash=_hash_password("agent-pass"),
        name="坐席七",
        status=status,
    )
    db.add(agent)
    db.commit()
    return agent


def test_normal_handoff_persists_reason(db):
    """服务时间内 + 在线坐席 → 正常转接，会话持久化转接原因。"""
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    _create_agent(db, status="online")

    trigger_handoff(db, conv, HandoffReason.EXPLICIT_REQUEST, now=datetime(2026, 1, 1, hour=10))

    db.refresh(conv)
    assert conv.handoff_reason == "explicit_request"


def test_offline_handoff_after_hours_persists_reason(db):
    """非服务时间 → 离线兜底（建回呼 Ticket），会话同样持久化转接原因。"""
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    _create_agent(db, status="online")

    trigger_handoff(db, conv, HandoffReason.COMPLIANCE_RISK, now=datetime(2026, 1, 1, hour=23))

    db.refresh(conv)
    assert conv.handoff_reason == "compliance_risk"


def test_str_reason_persisted_as_enum_value(db):
    """str reason 入参同样按枚举值持久化。"""
    customer = _create_customer(db)
    conv = _create_conversation(db, customer.id)
    _create_agent(db, status="online")

    trigger_handoff(db, conv, "negative_sentiment", now=datetime(2026, 1, 1, hour=10))

    db.refresh(conv)
    assert conv.handoff_reason == "negative_sentiment"
