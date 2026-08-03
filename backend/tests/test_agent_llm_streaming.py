"""B3 循环1 RED→GREEN：LLM 助理对话流基础（验收标准 1+3+4）。

PRD 依据：
  - 验收标准1：Assistant 接收用户消息 → LLM 生成回复 → 流式推送 token
  - 验收标准3：FakeListLLM 注入固定响应 → 对话流确定性可测
  - 验收标准4：ChatMessageHistory 持久化跨轮上下文

行为测试（不用内部 API，测可观察输出）：
  - 用可注入 FakeListLLM 返回固定 token 序列
  - Assistant.chat() 产出流式 token（逐 token 生成器）
  - 跨轮调用后 chat_history 含正确对话序列
  - System prompt 含问候/转接/合规静态话术（PRD 实现决策 › 知识来源）
"""

from __future__ import annotations

import pytest

from app.agent.llm import BaseLLM, ChatMessage, ChatRole, FakeListLLM
from app.agent.service import AssistantService


# ---------------------------------------------------------------------------
# 循环1-RED1：FakeListLLM 注入 + 流式 token 生成（行为：逐 token 产出）
# ---------------------------------------------------------------------------
class TestFakeLLMStreaming:
    @pytest.mark.anyio
    async def test_fake_llm_returns_tokens_one_by_one(self):
        """FakeListLLM 按列表顺序逐个产出 token（保证 CI 确定性）。"""
        tokens = ["你", "好", "，", "请", "问", "有", "什", "么", "可", "以", "帮", "您", "？"]
        llm: BaseLLM = FakeListLLM(responses=["".join(tokens)])
        # 对话历史（单轮 user 消息）
        history = [ChatMessage(role=ChatRole.USER, content="您好")]
        collected: list[str] = []
        async for tok in llm.stream(history):
            collected.append(tok)
        # 逐 token 生成（字符串拆分为字符级 token，模拟真实分段）
        assert collected == tokens

    @pytest.mark.anyio
    async def test_fake_llm_returns_full_text(self):
        """FakeListLLM invoke 返回完整文本（非流式接口）。"""
        llm = FakeListLLM(responses=["完整回复内容"])
        result = await llm.invoke([ChatMessage(role=ChatRole.USER, content="hi")])
        assert result == "完整回复内容"

    @pytest.mark.anyio
    async def test_fake_llm_cycles_responses(self):
        """多轮对话循环 responses 列表（超出时循环）。"""
        llm = FakeListLLM(responses=["第一轮", "第二轮"])
        h = [ChatMessage(role=ChatRole.USER, content="q1")]
        assert await llm.invoke(h) == "第一轮"
        assert await llm.invoke(h) == "第二轮"
        assert await llm.invoke(h) == "第一轮"  # 循环


# ---------------------------------------------------------------------------
# 循环1-RED2：AssistantService 流式对话（验收标准1 + 验收标准3）
# ---------------------------------------------------------------------------
class TestAssistantServiceStreaming:
    @pytest.fixture
    def svc(self) -> AssistantService:
        """注入 FakeListLLM 的 AssistantService，响应完全可预测。"""
        llm = FakeListLLM(responses=["你好，我是电信客服助理。", "当前话费余额为 58.20 元。"])
        return AssistantService(llm=llm)

    @pytest.mark.anyio
    async def test_assistant_chat_streams_tokens(self, svc: AssistantService):
        """Assistant.chat(user_text) 以 AsyncGenerator[str, None] 形式逐 token 推送。"""
        tokens: list[str] = []
        async for tok in svc.chat(conversation_id=1, user_message="您好"):
            tokens.append(tok)
        # FakeListLLM 第一轮响应的字符级 token
        assert "".join(tokens) == "你好，我是电信客服助理。"

    @pytest.mark.anyio
    async def test_assistant_chat_preserves_history_across_turns(self, svc: AssistantService):
        """跨轮对话：ChatMessageHistory 正确累积（验收标准4）。"""
        # 第一轮
        async for _ in svc.chat(conversation_id=42, user_message="查一下话费"):
            pass
        # 第二轮（同一 conversation_id → 历史共享）
        tokens: list[str] = []
        async for tok in svc.chat(conversation_id=42, user_message="还有流量呢？"):
            tokens.append(tok)
        # 第二轮响应应为 FakeListLLM 第二条
        assert "".join(tokens) == "当前话费余额为 58.20 元。"

        # 直接从 service 读取历史（行为级：历史应为 4 条 user/assistant 交替）
        history = svc.get_history(conversation_id=42)
        roles = [m.role for m in history]
        # system prompt 是第 0 条；然后 user, assistant, user, assistant
        assert roles[0] == ChatRole.SYSTEM
        assert roles[1:] == [
            ChatRole.USER,
            ChatRole.ASSISTANT,
            ChatRole.USER,
            ChatRole.ASSISTANT,
        ]

    @pytest.mark.anyio
    async def test_assistant_system_prompt_contains_static_prompts(self, svc: AssistantService):
        """System prompt 含：问候话术、合规提示、转接说明（PRD 实现决策 › 知识来源 › 静态话术）。"""
        history = svc.get_history(conversation_id=999)
        # 无对话时，get_history 返回仅含 system prompt 的初始化历史
        system_msg = next(m for m in history if m.role == ChatRole.SYSTEM)
        assert "电信客服" in system_msg.content  # 品牌身份
        assert "转接" in system_msg.content or "人工" in system_msg.content  # 转接触发说明
        # 合规：办理类需二次确认（PRD 实现决策 › 办理流程）
        assert "二次确认" in system_msg.content or "确认" in system_msg.content

    @pytest.mark.anyio
    async def test_different_conversations_have_isolated_history(self, svc: AssistantService):
        """不同 conversation_id 的历史严格隔离（无跨会话泄漏）。"""
        async for _ in svc.chat(conversation_id=1, user_message="我是会话1"):
            pass
        h1 = svc.get_history(conversation_id=1)
        h2 = svc.get_history(conversation_id=2)
        # 会话1：system + user + assistant = 3
        assert len([m for m in h1 if m.role != ChatRole.SYSTEM]) == 2
        # 会话2：仅 system（无用户消息）
        assert len([m for m in h2 if m.role != ChatRole.SYSTEM]) == 0
