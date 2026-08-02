"""B3 循环3 RED→GREEN：StreamingCallbacks 与 WS 事件解耦（验收标准1：llm.token 流式推送）。

PRD 依据：
  - 验收标准1：Assistant → LLM 生成 → 流式推送 `llm.token`
  - PRD #L282：WS 事件含 `llm.token`（LLM 流式 token）
  - PRD 测试决策 › WS 事件 seam：事件名与 frontend/shared/events.ts 镜像一致

行为测试（不启动 WS，通过回调注册 + 事件计数验证）：
  - chat() 期间逐 token 触发 on_token(token) 回调
  - tool 调用前后触发 on_tool_start(call) / on_tool_end(result) 回调
  - 这些回调是协议层（WS 路由）注入的，AssistantService 不直接依赖 ASGI/WebSocket
"""

from __future__ import annotations

import pytest

from app.agent.llm import FakeListLLM
from app.agent.service import AssistantService
from app.agent.tools import ToolCall, ToolContext, ToolRegistry, ToolResult, tool


class RecordingCallbacks:
    """回调收集器（供测试/WS 路由层复用模式）。"""

    def __init__(self) -> None:
        self.tokens: list[str] = []
        self.tool_starts: list[ToolCall] = []
        self.tool_ends: list[ToolResult] = []

    async def on_token(self, token: str) -> None:
        self.tokens.append(token)

    async def on_tool_start(self, call: ToolCall) -> None:
        self.tool_starts.append(call)

    async def on_tool_end(self, result: ToolResult) -> None:
        self.tool_ends.append(result)


class TestStreamingCallbacks:
    @pytest.fixture
    def svc(self) -> AssistantService:
        registry = ToolRegistry()

        @registry.register
        @tool(name="ping", description="返回 pong")
        def ping(ctx: ToolContext) -> str:
            return "pong"

        llm = FakeListLLM(
            responses=[
                "<|tool_call:ping:{}|>",
                "工具执行完成，结果为 pong。",
            ]
        )
        return AssistantService(llm=llm, tool_registry=registry)

    @pytest.mark.asyncio
    async def test_on_token_fired_per_token(self, svc: AssistantService):
        """chat 逐 token 触发 on_token；最终文本与 callbacks 收集一致。"""
        cb = RecordingCallbacks()
        tokens: list[str] = []
        async for tok in svc.chat(
            conversation_id=1, user_message="ping 一下", callbacks=cb
        ):
            tokens.append(tok)

        final_text = "".join(tokens)
        # callbacks.tokens 应与 chat() yield 的 tokens 完全一致
        assert "".join(cb.tokens) == final_text
        # 每个字符都是一次单独的 token 回调（伪 LLM 字符级）
        assert len(cb.tokens) == len(final_text)
        assert final_text == "工具执行完成，结果为 pong。"

    @pytest.mark.asyncio
    async def test_tool_start_end_callbacks(self, svc: AssistantService):
        """tool 调用前后触发 on_tool_start / on_tool_end；参数与结果一致。"""
        cb = RecordingCallbacks()
        async for _ in svc.chat(
            conversation_id=2, user_message="ping", callbacks=cb
        ):
            pass

        assert len(cb.tool_starts) == 1
        assert len(cb.tool_ends) == 1
        assert cb.tool_starts[0].name == "ping"
        assert cb.tool_ends[0].name == "ping"
        assert cb.tool_ends[0].success is True
        assert cb.tool_ends[0].content == "pong"
        # tool_call_id 对应（start.id == end.call_id）
        assert cb.tool_starts[0].id == cb.tool_ends[0].call_id

    @pytest.mark.asyncio
    async def test_callbacks_optional_none_safe(self, svc: AssistantService):
        """callbacks=None 或内部某个方法未实现时安全工作（不抛异常）。"""
        tokens: list[str] = []
        # callbacks=None
        async for tok in svc.chat(conversation_id=3, user_message="hi", callbacks=None):
            tokens.append(tok)
        # 无回调时仍可正常对话（最终回复：因 user_message=hi 后 LLM 首轮是 tool_call，
        # 但执行后第二轮响应是 "工具执行完成..."，见 responses[1]）
        assert tokens  # 非空
