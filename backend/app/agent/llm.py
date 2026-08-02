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

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum

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

    接口尽量小（深模块）：仅暴露 invoke(非流式) 与 stream(流式)，
    不关心具体 provider（OpenAI/本地/伪）。子类可：
      - 直接实现 stream()（如测试用的 _HistoryInspectingLLM），或
      - 包装 langchain BaseChatModel（如 FakeListLLM）。
    """

    def invoke(self, messages: list[ChatMessage]) -> str:
        """非流式：返回完整文本。默认实现委托 stream 并拼接。"""
        return "".join(self.stream(messages))

    def stream(self, messages: list[ChatMessage]) -> Iterator[str]:
        """流式：逐个产出 token（字符串片段，粒度由实现决定）。"""
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

    def stream(self, messages: list[ChatMessage]) -> Iterator[str]:
        # 将领域消息翻译为 langchain BaseMessage 后调用底层 chat model
        lc_messages = [_to_langchain_message(m) for m in messages]
        for chunk in self._chat_model.stream(lc_messages):
            content = chunk.content
            # FakeMessagesListChatModel 始终返回 str content；防御性处理 list/dict 形态
            if not isinstance(content, str):
                content = str(content)
            # 字符级分段：模拟真实流式输出（每片 1-2 字符，保证多 token 测试）
            yield from content
