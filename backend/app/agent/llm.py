"""B3 LLM 抽象与 ChatMessage 模型（深模块：可注入 BaseLLM 解耦测试）。

PRD 依据：
  - 实现决策 › 知识来源（三类来源之一：静态话术 Prompt 注入 system role）
  - 测试决策 › tool 调用 seam（FakeListLLM 保证对话流与 tool 调用逻辑确定性）

LangChain 集成：
  - `FakeListLLM` 内部包装 `langchain_core.language_models.fake_chat_models
    .FakeMessagesListChatModel`，复用其 responses 循环语义。
  - 通过 `_to_langchain_message` 把领域 `ChatMessage` 翻译为 langchain
    `BaseMessage`（SystemMessage/HumanMessage/AIMessage/ToolMessage）。
  - 领域层仍只依赖 `ChatRole`/`ChatMessage`，不泄漏 langchain 类型。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx
import structlog
from langchain_core.language_models.fake_chat_models import (
    FakeMessagesListChatModel,
)
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

logger = structlog.get_logger(__name__)


class ChatRole(str, Enum):
    """LangChain 兼容的聊天消息角色枚举（与 ChatMessage.role 对应）。"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"  # tool 调用结果（验收标准5：tool 记录不入 Message，仅入审计日志）


@dataclass(slots=True)
class ChatMessage:
    """通用 ChatMessage 数据类（LLM 层与对话层之间的传输对象）。

    与 B2 Message ORM 模型分工：
      - 本类：LLM 对话上下文（含 tool 临时记录等），用于 prompt 组装
      - app.models.conversation.Message：持久化的对话流消息（四类来源）
    验收标准5：ChatMessage 含 TOOL role 用于 LLM prompt，但持久化时不写入 Message 表。
    """

    role: ChatRole
    content: str
    #: tool 调用关联的 tool_call_id / tool_name（仅 TOOL role 使用）
    tool_call_id: str | None = None
    tool_name: str | None = None


def _to_langchain_message(msg: ChatMessage) -> BaseMessage:
    """领域 ChatMessage → langchain BaseMessage（内部翻译，不对外泄漏）。"""
    if msg.role is ChatRole.SYSTEM:
        return SystemMessage(content=msg.content)
    if msg.role is ChatRole.USER:
        return HumanMessage(content=msg.content)
    if msg.role is ChatRole.TOOL:
        # ToolMessage 必须携带 tool_call_id；缺失时用空串兜底（FakeListLLM 不消费）
        return ToolMessage(content=msg.content, tool_call_id=msg.tool_call_id or "")
    return AIMessage(content=msg.content)  # ASSISTANT


class BaseLLM:
    """LLM 抽象基类（seam：FakeListLLM 与真实 LLM 实现此接口）。

    接口尽量小（深模块）：仅暴露 invoke(非流式) 与 stream(流式)，两者均为
    **异步**接口（issue #67：同步 httpx 在 async 对话流中阻塞 asyncio 事件
    循环，导致多会话并发 + APScheduler 调度任务被拖卡）。子类可：
      - 直接实现 async stream()（如测试用的 _HistoryInspectingLLM），或
      - 包装 langchain BaseChatModel（如 FakeListLLM）。
    """

    async def invoke(self, messages: list[ChatMessage]) -> str:
        """非流式：返回完整文本。默认实现委托 stream 并拼接。"""
        return "".join([token async for token in self.stream(messages)])

    def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        """流式：逐个产出 token（字符串片段，粒度由实现决定）。

        声明为返回 AsyncIterator 的普通方法（非 async）而非 async def：
        mypy 将 `async def` 视为协程（Coroutine），与子类 async generator 的
        AsyncIterator 类型不兼容；去掉 async 后子类以 `async def ... yield`
        实现即可正确匹配（调用侧 `async for` 直接消费）。
        """
        raise NotImplementedError  # pragma: no cover - 子类实现


class FakeListLLM(BaseLLM):
    """伪 LLM：包装 langchain FakeMessagesListChatModel，循环返回固定字符串（CI 确定性）。

    PRD 依据：测试决策 › tool 调用 seam（FakeListLLM 验证对话流与 tool 调用逻辑）。
    行为契约（与 langchain FakeMessagesListChatModel 对齐）：
      - responses 列表非空（首轮至少 1 条）
      - 多轮调用按 cursor 循环取下一条；超出后回到开头
      - stream() 将完整响应按字符切分产出，模拟真实分段 token 行为
    """

    def __init__(self, responses: list[str]) -> None:
        if not responses:
            raise ValueError("FakeListLLM.responses 不能为空（至少 1 条用于首轮）")
        # 用 AIMessage 包装，使 langchain 端的响应类型与真实 chat model 一致
        self._chat_model = FakeMessagesListChatModel(
            responses=[AIMessage(content=r) for r in responses]
        )

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        # 将领域消息翻译为 langchain BaseMessage 后调用底层 chat model
        lc_messages = [_to_langchain_message(m) for m in messages]
        for chunk in self._chat_model.stream(lc_messages):
            content = chunk.content
            # FakeMessagesListChatModel 始终返回 str content；防御性处理 list/dict 形态
            if not isinstance(content, str):
                content = str(content)
            # 字符级分段：模拟真实流式输出（每片 1-2 字符，保证多 token 测试）
            for ch in content:
                yield ch


#: 追加到请求首部的 tool 调用协议说明（v1 简化协议 <|tool_call:name:json|>，
#: 与 app.agent.tools.parse_tool_call 对应）。独立注入请求而非改 SYSTEM_PROMPT，
#: 避免影响现有 FakeListLLM 行为测试。
_TOOL_PROTOCOL_PROMPT = (
    "工具调用协议：当用户请求涉及查询或办理业务（话费、套餐、用量、合约、增值业务、"
    "套餐变更、增值订退、停机保号、充值缴费）或查询公开信息（套餐介绍、营业厅、覆盖）时，"
    "你必须只输出一个工具调用标记且不输出任何其他文字，格式为：\n"
    '<|tool_call:工具名:{"参数名": "值"}|>\n'
    "参数必须使用双引号 JSON 格式；根据用户意图选择最合适的工具。"
    "其余情况正常回复用户。"
)


def _to_openai_message(msg: ChatMessage) -> dict[str, str]:
    """领域 ChatMessage → OpenAI 兼容 API 消息（v1 简化协议）。

    TOOL role 承载工具执行结果：OpenAI 原生 tool role 必须紧跟带 tool_calls 的
    assistant 消息（本协议未使用原生 tool 调用），故映射为 user role 并前缀标记，
    保证模型可见工具结果上下文。
    """
    if msg.role is ChatRole.TOOL:
        tool_label = f"[工具 {msg.tool_name} 结果] " if msg.tool_name else "[工具结果] "
        return {"role": "user", "content": f"{tool_label}{msg.content}"}
    role = {
        ChatRole.SYSTEM: "system",
        ChatRole.USER: "user",
        ChatRole.ASSISTANT: "assistant",
    }[msg.role]
    return {"role": role, "content": msg.content}


class OpenAICompatLLM(BaseLLM):
    """OpenAI 兼容 API 的真实 LLM（NVIDIA NIM / OpenAI / 兼容网关）。

    与 FakeListLLM 实现同一 BaseLLM 接口（B3 seam，接口不变仅换 provider）：
      - invoke：POST /chat/completions（非流式）返回完整文本
      - stream：POST stream=true，逐 SSE delta 产出 content 片段
    异步实现（issue #67）：内部使用 httpx.AsyncClient，全程 await——同步 httpx
    在 async 对话流中阻塞事件循环（调度任务延迟 19s、多会话并发卡死）。

    协议说明：请求头部注入 _TOOL_PROTOCOL_PROMPT（system），工具清单经
    tool_descriptions 由调用方（ws/routes 从 ToolRegistry.list_tools 生成）注入。
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.7,
        timeout_seconds: float = 60.0,
        tool_descriptions: str = "",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._tool_descriptions = tool_descriptions
        self._client = http_client or httpx.AsyncClient(timeout=timeout_seconds)

    # ------------------------------------------------------------------
    # 内部：请求组装
    # ------------------------------------------------------------------
    def _chat_url(self) -> str:
        # 约定 base_url 指向 API 根（如 https://integrate.api.nvidia.com/v1）或
        # 已含完整路径（如 https://apihub.agnes-ai.com/v1/chat/completions）
        base = self._base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _payload(self, messages: list[ChatMessage], *, stream: bool) -> dict[str, Any]:
        protocol: list[dict[str, str]] = [{"role": "system", "content": _TOOL_PROTOCOL_PROMPT}]
        if self._tool_descriptions:
            protocol.append({"role": "system", "content": f"可用工具：\n{self._tool_descriptions}"})
        return {
            "model": self._model,
            "messages": protocol + [_to_openai_message(m) for m in messages],
            "temperature": self._temperature,
            "stream": stream,
        }

    # ------------------------------------------------------------------
    # BaseLLM 接口（异步）
    # ------------------------------------------------------------------
    async def invoke(self, messages: list[ChatMessage]) -> str:
        resp = await self._client.post(
            self._chat_url(),
            headers=self._headers(),
            json=self._payload(messages, stream=False),
        )
        if resp.status_code != 200:
            raise RuntimeError(f"LLM API 调用失败（HTTP {resp.status_code}）：{resp.text[:200]}")
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "") or ""

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        payload = self._payload(messages, stream=True)
        async with self._client.stream(
            "POST", self._chat_url(), headers=self._headers(), json=payload
        ) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise RuntimeError(
                    f"LLM API 流式调用失败（HTTP {resp.status_code}）：{body[:200]!r}"
                )
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if content:
                    yield content


class FailoverLLM(BaseLLM):
    """LLM 主备自动切换：providers 依序尝试，当前 provider 抛错自动切下一个。

    实现同一 BaseLLM 接口（B3 seam 不变，异步语义同 #67）：
      - invoke：按序调用，异常 → 切换下一个，全部失败抛最后一个异常
      - stream：迭代当前 provider 输出；中途抛错（如 NVIDIA 529 过载）→
        从下一个 provider 重新生成完整回复
    全部 provider 失败时异常向上传播，由 AssistantService.chat() 兜底话术降级。
    切换事件经 structlog 记录（llm_provider_failed），便于观测哪家不可用。
    """

    def __init__(self, providers: list[BaseLLM]) -> None:
        if not providers:
            raise ValueError("FailoverLLM.providers 不能为空")
        self._providers = list(providers)

    async def invoke(self, messages: list[ChatMessage]) -> str:
        last_exc: Exception | None = None
        for provider in self._providers:
            try:
                return await provider.invoke(messages)
            except Exception as exc:  # noqa: BLE001 - 任一 provider 失败即切换
                last_exc = exc
                logger.warning(
                    "llm_provider_failed",
                    provider=type(provider).__name__,
                    error=str(exc),
                )
        assert last_exc is not None
        raise last_exc

    async def stream(self, messages: list[ChatMessage]) -> AsyncIterator[str]:
        last_exc: Exception | None = None
        for provider in self._providers:
            try:
                async for token in provider.stream(messages):
                    yield token
                return
            except Exception as exc:  # noqa: BLE001 - 流式中途失败切换下一个
                last_exc = exc
                logger.warning(
                    "llm_provider_failed",
                    provider=type(provider).__name__,
                    error=str(exc),
                )
        assert last_exc is not None
        raise last_exc
