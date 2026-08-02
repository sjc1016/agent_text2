"""B2 循环3：Message 四类来源分类 + 助理 tool 内部记录不入对话流。

验收标准（issue #7）：
  Message 四类来源（用户/助理/坐席/系统）正确分类；
  助理 tool 调用内部记录不入对话流
  （PRD 依据：CONTEXT.md › 消息；用户故事 US-16, US-22）

CONTEXT › 消息：Message 按来源分四类——用户/助理/坐席/系统；
助理调用 tools 的内部记录不属于 Message，不入对话流，仅入审计日志。
本切片通过 service 层 create_message 守卫 source 合法性（B3 tool 框架复用本接口）。
"""

from sqlalchemy import select

from app.conversation.service import create_message
from app.models import Conversation, Message

_FOUR_SOURCES = ("user", "assistant", "agent", "system")


def test_create_message_accepts_four_sources(db):
    conv = Conversation(customer_id=None, status="unauthenticated")
    db.add(conv)
    db.flush()

    for source in _FOUR_SOURCES:
        msg = create_message(db, conv.id, source, f"{source} 内容")
        assert msg.source == source
        assert msg.content == f"{source} 内容"
    db.commit()

    msgs = list(db.execute(select(Message).where(Message.conversation_id == conv.id)).scalars())
    assert len(msgs) == 4
    assert {m.source for m in msgs} == set(_FOUR_SOURCES)


def test_create_message_rejects_invalid_source(db):
    conv = Conversation(customer_id=None, status="unauthenticated")
    db.add(conv)
    db.flush()

    # 非四类来源必须拒绝（含 tool 内部记录、bot、空串、大小写变体）
    for invalid in ("tool", "bot", "ai", "", "USER", "User"):
        try:
            create_message(db, conv.id, invalid, "内容")
        except ValueError:
            continue
        raise AssertionError(f"source={invalid!r} 应被拒绝，却创建成功")


def test_tool_internal_record_not_persisted_as_message(db):
    """助理 tool 调用内部记录不入对话流（CONTEXT › 消息）。

    source=tool 被拒绝后，DB 中该会话无任何消息——证明 tool 内部记录不进对话流。
    """
    conv = Conversation(customer_id=None, status="unauthenticated")
    db.add(conv)
    db.flush()

    try:
        create_message(db, conv.id, "tool", "内部 tool 调用记录")
    except ValueError:
        pass
    else:
        raise AssertionError("source=tool 不应创建 Message")

    db.commit()
    msgs = list(db.execute(select(Message).where(Message.conversation_id == conv.id)).scalars())
    assert len(msgs) == 0
