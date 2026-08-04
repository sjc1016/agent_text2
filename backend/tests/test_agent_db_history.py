"""B3 循环4 RED→GREEN：对话记忆与 B2 Conversation/Message 集成（验收标准4 持久化）。

PRD 依据：
  - 验收标准4：消息历史经 ChatMessageHistory 持久化，跨轮上下文保留
  - CONTEXT › 消息：Message 四类来源 user/assistant/agent/system（不含 tool）
  - B2 提供 conversation/list_messages_for_conversation(db, conversation_id)

行为测试（使用 conftest.db + ORM 播种，不启动 HTTP）：
  - 先创建 Conversation，再用 B2 service 播种几条 Message（user/assistant 交替）
  - AssistantService.load_history_from_db() 将 ORM 消息导入内部 ChatMessageHistory
  - 后续 chat() 时 LLM 能看到完整历史
  - save_messages_to_db() 将 user/assistant 消息回写 ORM
    （SYSTEM 不写，TOOL 不写 — 验收标准5）
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agent.llm import BaseLLM, ChatMessage, ChatRole, FakeListLLM
from app.agent.service import AssistantService
from app.conversation.service import create_message, list_messages_for_conversation
from app.models import Conversation, Customer


class _HistoryInspectingLLM(BaseLLM):
    """LLM 伪实现：把每次 stream() 收到的 messages 存到外部列表，再返回固定串。"""

    def __init__(
        self,
        seen_histories: list[list[ChatMessage]],
        response: str = "ok",
    ) -> None:
        self.seen_histories = seen_histories
        self.response = response

    async def stream(self, messages):
        self.seen_histories.append([ChatMessage(role=m.role, content=m.content) for m in messages])
        for ch in self.response:
            yield ch


def _seed_customer_and_conversation(db: Session) -> tuple[Customer, Conversation]:
    """播种一个客户与一条会话（无消息）。"""
    from app.auth.security import hash_password

    cust = Customer(
        phone="13800000001",
        service_password_hash=hash_password("SvcPass123"),
    )
    db.add(cust)
    db.flush()
    conv = Conversation(customer_id=cust.id, status="authenticated")
    db.add(conv)
    db.flush()
    return cust, conv


class TestDbHistoryIntegration:
    def test_load_from_db_imports_messages_in_order(self, db: Session):
        """load_history_from_db：ORM 消息按 created_at 升序写入 ChatMessageHistory。"""
        _cust, conv = _seed_customer_and_conversation(db)
        # 播种 user → assistant → user 三轮
        create_message(db, conversation_id=conv.id, source="user", content="我是第一轮用户")
        create_message(db, conversation_id=conv.id, source="assistant", content="第一轮助理回复")
        create_message(db, conversation_id=conv.id, source="user", content="我是第二轮用户")
        db.commit()

        svc = AssistantService(llm=FakeListLLM(responses=["答"]))
        # 载入历史
        svc.load_history_from_db(db, conversation_id=conv.id)

        history = svc.get_history(conv.id)
        # SYSTEM prompt 首条 + 3 ORM = 4
        assert len(history) == 4
        assert history[0].role == ChatRole.SYSTEM
        assert history[1].role == ChatRole.USER
        assert history[1].content == "我是第一轮用户"
        assert history[2].role == ChatRole.ASSISTANT
        assert history[2].content == "第一轮助理回复"
        assert history[3].role == ChatRole.USER
        assert history[3].content == "我是第二轮用户"

    def test_loaded_history_is_seen_by_llm(self, db: Session):
        """载入的历史正确传递给下一次 LLM 调用。"""
        _cust, conv = _seed_customer_and_conversation(db)
        create_message(db, conv.id, source="user", content="历史用户提问")
        db.commit()

        seen: list[list[ChatMessage]] = []
        llm = _HistoryInspectingLLM(seen, response="好的")
        svc = AssistantService(llm=llm)
        svc.load_history_from_db(db, conv.id)

        # 新对话轮
        collected: list[str] = []

        import asyncio

        async def _run() -> None:
            async for tok in svc.chat(conversation_id=conv.id, user_message="新提问"):
                collected.append(tok)

        asyncio.run(_run())
        # 此次 LLM.stream() 接收到的 messages 应含：SYSTEM + 历史USER + 新USER（共3条）
        assert len(seen) == 1
        last_call_msgs = seen[0]
        roles = [m.role for m in last_call_msgs]
        assert roles == [ChatRole.SYSTEM, ChatRole.USER, ChatRole.USER]
        assert last_call_msgs[1].content == "历史用户提问"
        assert last_call_msgs[2].content == "新提问"

    def test_save_persistable_messages_to_db_writes_new_messages_only(self, db: Session):
        """save_messages_to_db：增量写入 DB 中尚未入库的新消息。"""
        _cust, conv = _seed_customer_and_conversation(db)
        create_message(db, conv.id, source="user", content="DB 已有用户消息")
        db.commit()
        assert len(list_messages_for_conversation(db, conv.id)) == 1

        svc = AssistantService(llm=FakeListLLM(responses=["助理新回复"]))
        svc.load_history_from_db(db, conv.id)  # SYSTEM + 用户

        # 生成一轮 assistant 新消息
        import asyncio

        async def _run() -> None:
            async for _ in svc.chat(conversation_id=conv.id, user_message="我发了新的"):
                pass

        asyncio.run(_run())
        # 内部历史：SYSTEM + 旧USER + 新USER + 新ASSISTANT = 4
        # DB 目前只有 1
        written = svc.save_messages_to_db(db, conv.id)
        # 写入的一定是「DB 里没有」的 USER（"我发了新的"） + ASSISTANT（"助理新回复"）共 2 条
        assert len(list_messages_for_conversation(db, conv.id)) == 1 + len(written)
        assert len(written) == 2
        sources = sorted(m.source for m in written)
        assert sources == ["assistant", "user"]

    def test_save_does_not_write_tool_messages(self, db: Session):
        """验收标准5：TOOL role 消息永远不写入 Message 表。"""
        _cust, conv = _seed_customer_and_conversation(db)
        db.commit()
        assert len(list_messages_for_conversation(db, conv.id)) == 0

        from app.agent.tools import ToolContext, ToolRegistry, tool

        registry = ToolRegistry()

        @registry.register
        @tool(name="t", description="d")
        def _t(ctx: ToolContext) -> str:
            return "result"

        llm = FakeListLLM(responses=["<|tool_call:t:{}|>", "final"])
        svc = AssistantService(llm=llm, tool_registry=registry)

        import asyncio

        async def _run() -> None:
            async for _ in svc.chat(conversation_id=conv.id, user_message="go"):
                pass

        asyncio.run(_run())

        written = svc.save_messages_to_db(db, conv.id)
        # 可写：SYSTEM（不写，因为本项目 Message source 允许 system，但策略是
        # 永远不把 SYSTEM prompt 写 DB；由调用方决定；此处 save 仅追加 USER/ASSISTANT）
        # 写：USER("go") + ASSISTANT("<|tool_call|>") + ASSISTANT("final") — 但
        # get_persistable_messages 过滤 TOOL，保留 USER+ASSISTANT+SYSTEM；
        # save_messages_to_db 再跳过 SYSTEM。
        sources = [m.source for m in written]
        # TOOL 不在其中
        assert "tool" not in sources
        # 至少有 user / assistant 两类
        assert "user" in sources
        assert "assistant" in sources
