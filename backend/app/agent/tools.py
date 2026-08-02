"""B3 Tool 注册框架（纯函数 + 注册表；与 LLM 解耦可独立测试）。

PRD 依据：
  - 实现决策 › 模块划分（agent 模块承载 tools）
  - 测试决策 › tool 调用 seam（LangChain tools 作为纯函数测试，与 LLM 调用解耦）
  - 验收标准2：tools 注册为纯函数，可独立测试
  - 验收标准5：tool 调用内部记录仅入审计日志（ToolContext.audit_hook 回调），
    不入对话流 Message 表。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - 协议参数类型注解仅 mypy 需要
    # 避免 StreamingCallbacks ↔ ToolCall/ToolResult 的前向引用循环
    from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# 数据类（纯值对象，无逻辑）—— 必须先定义，供 StreamingCallbacks 协议签名引用
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class ToolContext:
    """tool 调用上下文（入参容器 + 审计 hook + 数据库会话）。"""

    customer_id: int | None = None  # 认证客户 ID；Visitor 场景为 None
    conversation_id: int | None = None
    params: dict = field(default_factory=dict)
    #: 审计 hook（可选）；由调用方注入，tool 内部在关键节点调用
    audit_hook: Callable[[dict], None] | None = None
    #: 数据库会话（可选）；业务 tool（查询/办理/咨询）经此访问数据，
    #: 由调用方（WS 路由 / 测试）注入，保持 tool 为可测纯函数
    db: Session | None = None


@dataclass(slots=True)
class BaseTool:
    """已注册工具的元数据（由 @tool 装饰器构造）。"""

    name: str
    description: str
    fn: Callable[[ToolContext], str]

    def __call__(self, ctx: ToolContext) -> str:
        return self.fn(ctx)


@dataclass(slots=True)
class ToolCall:
    """一次 tool 调用请求（从 LLM 输出解析）。"""

    id: str  # tool_call_id（唯一，用于关联 TOOL role message）
    name: str
    params: dict


@dataclass(slots=True)
class ToolResult:
    """一次 tool 调用结果。"""

    call_id: str
    name: str
    success: bool
    content: str
    error: str | None = None


# ---------------------------------------------------------------------------
# StreamingCallbacks 协议（与 WS 事件路由解耦；WS 路由层实现此协议）
# ---------------------------------------------------------------------------
@runtime_checkable
class StreamingCallbacks(Protocol):
    """Assistant 对话期间的流式回调协议（WS 路由层实现）。

    所有方法均可 async（允许 WS 发送等异步 I/O），且均可缺省（AssistantService
    调用前用 hasattr/getattr 安全检测）。
    """

    async def on_token(self, token: str) -> None:
        """每生成一个 token（字符串片段）时触发；对应 WS 事件 `llm.token`。"""
        ...  # pragma: no cover - 协议占位

    async def on_tool_start(self, call: ToolCall) -> None:
        """tool 调用开始时触发（供 UI 显示 "正在调用工具…"）。"""
        ...  # pragma: no cover - 协议占位

    async def on_tool_end(self, result: ToolResult) -> None:
        """tool 调用结束（成功/失败均触发）时触发。"""
        ...  # pragma: no cover - 协议占位


# ---------------------------------------------------------------------------
# @tool 装饰器 & ToolRegistry
# ---------------------------------------------------------------------------
def tool(*, name: str, description: str) -> Callable[[Callable], Callable]:
    """将纯函数标记为 tool（附加元数据属性，供 ToolRegistry.register 读取）。

    用法：
        @registry.register
        @tool(name="get_balance", description="查询话费余额")
        def get_balance(ctx: ToolContext) -> str:
            ...
    """

    def decorator(fn: Callable) -> Callable:
        fn._tool_meta = BaseTool(name=name, description=description, fn=fn)  # type: ignore[attr-defined]
        return fn

    return decorator


class ToolRegistry:
    """工具注册表（纯函数注册中心；验收标准2：可独立测试）。"""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    # -- 注册 --------------------------------------------------------------
    def register(self, fn: Callable) -> Callable:
        """注册 @tool 装饰过的函数；返回原函数便于堆叠装饰器。"""
        meta: BaseTool | None = getattr(fn, "_tool_meta", None)
        if meta is None:
            raise TypeError(
                f"{fn.__name__} 不是 @tool 装饰的函数，请先 @tool(name=..., description=...)"
            )
        if meta.name in self._tools:
            raise ValueError(f"工具名冲突：{meta.name} 已注册")
        self._tools[meta.name] = meta
        return fn

    # -- 查询 --------------------------------------------------------------
    def list_tools(self) -> list[BaseTool]:
        """按 name 排序返回已注册工具清单（供 LLM 选择）。"""
        return sorted(self._tools.values(), key=lambda t: t.name)

    def has(self, name: str) -> bool:
        return name in self._tools

    # -- 执行 --------------------------------------------------------------
    def invoke(self, name: str, ctx: ToolContext) -> str:
        """按名调用工具（纯函数调用，不涉及 LLM）。

        Raises:
            LookupError: 工具未注册
            Exception:   tool 函数自身抛出（调用方负责审计/包装错误）
        """
        if name not in self._tools:
            raise LookupError(f"工具未注册：{name!r}，已注册：{sorted(self._tools)}")
        return self._tools[name](ctx)

    def execute_call(self, call: ToolCall, ctx: ToolContext) -> ToolResult:
        """执行一次 ToolCall，返回 ToolResult（统一成功/失败封装）。

        调用 audit_hook（若有）记录 tool_call 事件（验收标准5：仅入审计日志）。
        """
        tool_ctx = ToolContext(
            customer_id=ctx.customer_id,
            conversation_id=ctx.conversation_id,
            params=dict(call.params),
            audit_hook=ctx.audit_hook,
        )
        try:
            content = self.invoke(call.name, tool_ctx)
            ok = True
            err = None
        except Exception as e:  # noqa: BLE001 - tool 错误统一收敛到 ToolResult
            content = ""
            ok = False
            err = f"{type(e).__name__}: {e}"

        result = ToolResult(call_id=call.id, name=call.name, success=ok, content=content, error=err)
        if ctx.audit_hook is not None:
            ctx.audit_hook(
                {
                    "type": "tool_call",
                    "tool_name": call.name,
                    "tool_call_id": call.id,
                    "params": call.params,
                    "success": ok,
                    "error": err,
                }
            )
        return result


# ---------------------------------------------------------------------------
# LLM 输出 ↔ ToolCall 解析（确定性 seam）
# ---------------------------------------------------------------------------

#: LLM 输出中的 tool_call 标记约定（v1 简化协议，真实实现换成 LangChain bind_tools 输出）
#: 格式：<|tool_call:tool_name:json_params_string|>
_TOOL_CALL_PREFIX = "<|tool_call:"
_TOOL_CALL_SUFFIX = "|>"


def parse_tool_call(text: str) -> ToolCall | None:
    """解析 LLM 输出中的 tool_call 标记；未找到返回 None。

    本项目 v1 采用简化伪协议 <|tool_call:name:json|> 便于 FakeListLLM 触发；
    真实 LLM 接入时替换为 LangChain 的 AIMessage.tool_calls 解析即可，接口保持不变。
    """
    s = text.strip()
    if not (s.startswith(_TOOL_CALL_PREFIX) and s.endswith(_TOOL_CALL_SUFFIX)):
        return None
    inner = s[len(_TOOL_CALL_PREFIX) : -len(_TOOL_CALL_SUFFIX)]
    first_colon = inner.find(":")
    if first_colon == -1:
        return None
    name = inner[:first_colon]
    params_json = inner[first_colon + 1 :]
    try:
        params = json.loads(params_json) if params_json else {}
    except json.JSONDecodeError:
        # JSON 非法时视为空参数（真实 LLM 接入时抛错；v1 容错保证 CI）
        params = {}
    if not isinstance(params, dict):
        params = {}
    return ToolCall(id=f"call_{uuid.uuid4().hex[:8]}", name=name, params=params)


def make_tool_call_marker(name: str, params: dict | None = None) -> str:
    """构造 tool_call 标记字符串（供伪 LLM / 测试用例使用）。"""
    params_json = json.dumps(params or {}, ensure_ascii=False, sort_keys=True)
    return f"{_TOOL_CALL_PREFIX}{name}:{params_json}{_TOOL_CALL_SUFFIX}"
