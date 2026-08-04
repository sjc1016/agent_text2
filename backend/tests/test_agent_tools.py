"""B3 循环2 RED→GREEN：Tool 调用框架（验收标准2+3+5）。

PRD 依据：
  - 验收标准2：tools 注册为纯函数，与 LLM 调用解耦，可独立测试
  - 验收标准3：FakeListLLM 注入含 tool_call 的多轮响应 → tool 调用逻辑确定性
  - 验收标准5：tool 调用内部记录不入对话流（Message 表），仅入审计日志

行为测试：
  - ToolRegistry 装饰器注册纯函数，可独立 invoke（不依赖 LLM）
  - AssistantService + FakeListLLM 多轮（tool_call → assistant 产出特殊标记 →
    service 解析 → 执行 tool → 追加 tool_result → 再次 LLM 生成最终回复）
  - tool 调用过程产出审计记录（audit hook，持久化由调用方负责），但 chat 最终对话流不含 tool 中间态
"""

from __future__ import annotations

import pytest

from app.agent.llm import ChatRole, FakeListLLM
from app.agent.service import AssistantService
from app.agent.tools import (
    ToolContext,
    ToolRegistry,
    tool,
)


# ---------------------------------------------------------------------------
# RED 2-1：ToolRegistry + @tool 装饰器注册纯函数（验收标准2：可独立测试）
# ---------------------------------------------------------------------------
class TestToolRegistry:
    def test_tool_decorator_registers_function(self):
        """@tool 装饰器将纯函数注册为 Tool，可通过 registry 按名调用。"""
        registry = ToolRegistry()

        @registry.register
        @tool(name="get_balance", description="查询当前话费余额")
        def get_balance(ctx: ToolContext) -> str:
            # 纯函数：不依赖外部，返回固定余额（真实实现由 B5 查询类切片填充）
            return "当前话费余额 58.20 元"

        # 独立调用（不经过 LLM）
        result = registry.invoke("get_balance", ToolContext(customer_id=1))
        assert "58.20" in result

    def test_tool_decorator_with_args(self):
        """带参数 tool：从 ToolContext.params 读取入参。"""
        registry = ToolRegistry()

        @registry.register
        @tool(name="query_usage", description="查询用量（类型: 通话/流量）")
        def query_usage(ctx: ToolContext) -> str:
            usage_type = ctx.params.get("type", "all")
            if usage_type == "call":
                return "通话分钟：已用 120 分钟，剩余 80 分钟"
            return "总用量摘要"

        r = registry.invoke("query_usage", ToolContext(customer_id=1, params={"type": "call"}))
        assert "120" in r

    def test_registry_list_tools_returns_sorted_list(self):
        """registry.list_tools() 返回已注册工具清单（供 LLM 挑选）。"""
        registry = ToolRegistry()

        @registry.register
        @tool(name="t1", description="工具1")
        def t1(ctx):
            return "r1"

        @registry.register
        @tool(name="t2", description="工具2")
        def t2(ctx):
            return "r2"

        tools = registry.list_tools()
        names = [t.name for t in tools]
        assert sorted(names) == ["t1", "t2"]

    def test_invoke_unknown_tool_raises(self):
        """调用未注册工具抛 ToolNotFoundError（含清晰错误信息）。"""
        registry = ToolRegistry()
        with pytest.raises(LookupError, match="未注册"):
            registry.invoke("nonexistent", ToolContext(customer_id=1))


# ---------------------------------------------------------------------------
# RED 2-2：AssistantService 编排 tool 调用（验收标准2+3+5）
# ---------------------------------------------------------------------------


class FakeToolCallingLLM(FakeListLLM):
    """带 tool_call 能力的伪 LLM：首轮返回 `<|tool_call|>` 标记，service 解析为 tool 调用。

    验收标准3：用注入的确定性响应验证 tool 调用逻辑。
    responses 约定：
      - 含 `<|tool_call:name:json_params|>` 标记的字符串 → 触发 tool_call
      - 后续普通字符串 → tool 执行后 LLM 最终回复
    """

    async def stream(self, messages):
        # 找到最后一条消息；若是 TOOL role，则跳过 cycling 直接取下一条响应
        # 简化实现：父类行为 + 循环 cursor 即可
        async for token in super().stream(messages):
            yield token


class TestAssistantToolCalling:
    @pytest.fixture
    def registry(self) -> ToolRegistry:
        r = ToolRegistry()

        @r.register
        @tool(name="get_balance", description="查话费余额")
        def gb(ctx: ToolContext) -> str:
            return "话费余额：58.20 元"

        return r

    @pytest.fixture
    def svc(self, registry: ToolRegistry) -> AssistantService:
        # 响应序列：首轮触发 tool_call（get_balance），次轮返回最终回复
        llm = FakeToolCallingLLM(
            responses=[
                "<|tool_call:get_balance:{}|>",
                "好的，已为您查询到：话费余额 58.20 元。",
            ]
        )
        return AssistantService(llm=llm, tool_registry=registry)

    @pytest.mark.asyncio
    async def test_assistant_invokes_tool_and_returns_final_answer(self, svc: AssistantService):
        """Assistant 自动执行 tool 调用 → 追加 tool_result → 再次 LLM → 返回最终回复。"""
        tokens: list[str] = []
        audit_events: list[dict] = []

        # 挂载审计 hook（验收标准5：tool 调用仅入审计日志，不入对话流 Message）
        def audit_hook(event: dict) -> None:
            audit_events.append(event)

        # 临时 monkey patch audit hook（实际注入应在构造函数；此处直接赋值给实例属性）
        svc.audit_hook = audit_hook

        async for tok in svc.chat(conversation_id=1, user_message="查话费"):
            tokens.append(tok)

        final_text = "".join(tokens)
        # 最终输出应为第二条响应（tool 调用完成后的最终回复）
        assert final_text == "好的，已为您查询到：话费余额 58.20 元。"
        # 审计日志应记录 tool 调用（不含对话流 message.new 中间态）
        tool_events = [e for e in audit_events if e.get("type") == "tool_call"]
        assert len(tool_events) == 1
        assert tool_events[0]["tool_name"] == "get_balance"
        assert tool_events[0]["success"] is True

    @pytest.mark.asyncio
    async def test_tool_result_in_history_but_not_marked_for_message(self, svc: AssistantService):
        """验收标准5：TOOLS 消息在 LLM prompt 历史中用于上下文，但持久化时不应写入 Message 表。

        具体：service 对该条是 LLM prompt 内存历史中有 role=TOOL 的 ChatMessage，
        但对外接口 get_persistable_messages() 只返回 user/assistant/system（不含 TOOL）。
        """
        async for _ in svc.chat(conversation_id=7, user_message="查一下话费"):
            pass

        # 内部完整历史（含 TOOL）
        raw = svc.get_history(7)
        roles_raw = {m.role for m in raw}
        assert ChatRole.TOOL in roles_raw  # 内存中有 TOOL（供下次 LLM prompt）

        # 可持久化消息（验收标准5：给 conversation service 写入 Message 表时用此接口）
        persistable = svc.get_persistable_messages(7)
        roles_persist = {m.role for m in persistable}
        assert ChatRole.TOOL not in roles_persist  # 不写入对话流
