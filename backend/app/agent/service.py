"""B3 AssistantService：LLM 对话流 + Tool 编排 + 对话记忆（深模块）。

PRD 依据：
  - 实现决策 › 模块划分（agent 模块：LangChain 助理与 tools）
  - 实现决策 › 知识来源（静态话术 Prompt 写入 system prompt）
  - 测试决策 › tool 调用 seam（tools 纯函数与 LLM 解耦，FakeListLLM 验证）
  - 验收标准1：流式 token 推送
  - 验收标准2：tool 注册为纯函数，可独立测试
  - 验收标准3：FakeListLLM 保证确定性
  - 验收标准4：ChatMessageHistory 跨轮上下文
  - 验收标准5：tool 调用记录仅入审计日志，不入对话流 Message 表
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.orm import Session

from .llm import BaseLLM, ChatMessage, ChatRole
from .tools import (
    StreamingCallbacks,
    ToolCall,
    ToolContext,
    ToolRegistry,
    ToolResult,
    parse_tool_call,
)

if TYPE_CHECKING:  # pragma: no cover
    pass

logger = structlog.get_logger(__name__)


async def _safe_cb(
    cb: StreamingCallbacks | None,
    method: str,
    *args: object,
) -> None:
    """安全调用 StreamingCallbacks 上的方法（方法不存在/抛错均忽略，避免中断对话流）。"""
    if cb is None:
        return
    fn: Callable[..., Awaitable[Any]] | None = getattr(cb, method, None)
    if fn is None:
        return
    with contextlib.suppress(Exception):
        await fn(*args)


#: System prompt（PRD 实现决策 › 知识来源 › 静态话术 Prompt）
SYSTEM_PROMPT = (
    "你是中国电信官方客服助理。"
    "当用户咨询公开信息（套餐介绍、网络覆盖、营业厅地址）时直接回答；"
    "当用户查询与号码绑定的业务（话费、套餐详情、用量、合约、增值业务）时，"
    "请确认对方已认证后再调用查询工具；"
    "当用户请求办理类业务（套餐变更、增值业务订退、停机保号、充值缴费）时，"
    "**必须先发起二次确认**，结构化说明业务影响（套餐对比、生效时间、合约影响、费用变化），"
    "用户显式确认后才创建工单，不得直接办理。"
    "以下场景自动触发转接人工坐席（Handoff）："
    "1) 超出能力范围；2) 办理失败；3) 用户明确要求转人工；"
    "4) 检测到强烈负面情绪；5) 同一意图连续 3 轮未完成；6) 涉及合规争议。"
    "回复请简洁专业，符合电信客服语气。"
)


@dataclass
class AssistantService:
    """Assistant 主服务（可注入 LLM 与 ToolRegistry 便于测试）。

    模块边界（PRD 实现决策 › 模块划分）：
      - 本服务负责 LLM 对话流、上下文管理、tool 调用编排
      - 不直接写 DB：持久化由调用方（conversation service / audit 模块）负责
      - TOOL role 的 ChatMessage 仅保留在内存 history 用于 LLM prompt，
        get_persistable_messages() 过滤后不含 TOOL（验收标准5）。
    """

    llm: BaseLLM
    tool_registry: ToolRegistry | None = None
    #: 审计 hook（可选）：tool_call 事件、llm 事件回调
    audit_hook: Callable[[dict], None] | None = None
    #: conversation_id → ChatMessageHistory（内存历史）
    _histories: dict[int, list[ChatMessage]] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # 对外接口：流式对话
    # ------------------------------------------------------------------
    async def chat(
        self,
        conversation_id: int,
        user_message: str,
        customer_id: int | None = None,
        callbacks: StreamingCallbacks | None = None,
        db: Session | None = None,
        audit_hook: Callable[[dict], None] | None = None,
    ) -> AsyncGenerator[str, None]:
        """发送用户消息 → LLM 流式生成（自动编排 tool 调用 + StreamingCallbacks）。

        db / audit_hook：按调用（WS 路由等）注入的 tool 上下文依赖——业务 tool
        经 ToolContext.db 访问数据库、经 audit_hook 留痕；缺省回退服务级字段
        （self.db 不存在，仅 self.audit_hook）。保持服务对传输层与请求级会话无感知。

        行为（最多 MAX_TOOL_CYCLES 次 tool 调用，防止死循环）：
          1. 追加 user message
          2. LLM 流式生成；对正常回复逐 token yield + 逐 token on_token() 回调
          3. 若 LLM 输出为 tool_call → on_tool_start() → 执行 → on_tool_end()
             → 追加 TOOL message → 回到 2
          4. 否则最终回复已产出，返回
        """
        history = self._get_or_init_history(conversation_id)
        history.append(ChatMessage(role=ChatRole.USER, content=user_message))

        max_cycles = 5
        for _ in range(max_cycles):
            raw_tokens: list[str] = []
            try:
                for token in self.llm.stream(history):
                    raw_tokens.append(token)
            except Exception as exc:  # noqa: BLE001 - LLM provider 错误（过载/超时）兜底
                # 真实 LLM（如 NVIDIA 529 过载）瞬时失败时降级为提示话术，
                # 保证 chat() 契约「必然产出回复」，不中断 WS 连接。
                logger.warning(
                    "llm_stream_failed",
                    conversation_id=conversation_id,
                    error=str(exc),
                )
                fallback = "抱歉，当前服务繁忙，请稍后重试。"
                for ch in fallback:
                    await _safe_cb(callbacks, "on_token", ch)
                    yield ch
                history.append(ChatMessage(role=ChatRole.ASSISTANT, content=fallback))
                return
            llm_output = "".join(raw_tokens)

            call: ToolCall | None = parse_tool_call(llm_output)
            if call is None or self.tool_registry is None:
                # 正常回复：逐 token yield + on_token 回调
                for tok in raw_tokens:
                    await _safe_cb(callbacks, "on_token", tok)
                    yield tok
                history.append(ChatMessage(role=ChatRole.ASSISTANT, content=llm_output))
                return

            # tool_call：内部执行，不对外产出中间 tokens
            history.append(ChatMessage(role=ChatRole.ASSISTANT, content=llm_output))
            await _safe_cb(callbacks, "on_tool_start", call)
            ctx = ToolContext(
                customer_id=customer_id,
                conversation_id=conversation_id,
                audit_hook=audit_hook or self.audit_hook,
                db=db,
            )
            result: ToolResult = self.tool_registry.execute_call(call, ctx)
            await _safe_cb(callbacks, "on_tool_end", result)
            history.append(
                ChatMessage(
                    role=ChatRole.TOOL,
                    content=(result.content if result.success else f"[错误] {result.error}"),
                    tool_call_id=result.call_id,
                    tool_name=result.name,
                )
            )
            # 继续下一轮 LLM 生成

        # 超出最大循环：兜底回复
        fallback = "抱歉，处理过程中出现异常，请稍后重试。"
        for ch in fallback:
            await _safe_cb(callbacks, "on_token", ch)
            yield ch
        history.append(ChatMessage(role=ChatRole.ASSISTANT, content=fallback))

    # ------------------------------------------------------------------
    # 对外接口：历史消息
    # ------------------------------------------------------------------
    def get_history(self, conversation_id: int) -> list[ChatMessage]:
        """只读返回完整内部历史（含 SYSTEM + TOOL，供调试/观察）。"""
        return list(self._get_or_init_history(conversation_id))

    def get_persistable_messages(self, conversation_id: int) -> list[ChatMessage]:
        """返回可持久化到 Message 表的消息（验收标准5：过滤 TOOL role）。

        CONTEXT › 消息：Message 仅四类来源 user/assistant/agent/system；
        tool 调用中间记录不属于 Message，故过滤掉 TOOL role。
        """
        return [
            m
            for m in self._get_or_init_history(conversation_id)
            if m.role in {ChatRole.USER, ChatRole.ASSISTANT, ChatRole.SYSTEM}
        ]

    # ------------------------------------------------------------------
    # 对外接口：历史消息持久化 ↔ DB（B2 Conversation/Message 集成）
    # ------------------------------------------------------------------
    def load_history_from_db(self, db: Session, conversation_id: int) -> None:
        """从 B2 Message ORM 载入会话历史到内存 history（追加到 SYSTEM prompt 之后）。

        幂等：重复调用不重复载入（首调后 history 已长于 SYSTEM，之后不再重放）。
        依赖：conversation.service.list_messages_for_conversation（B2）。
        """
        from app.conversation.service import list_messages_for_conversation
        from app.models.conversation import MessageSource

        existing = self._histories.get(conversation_id)
        if existing is None:
            # 先初始化（首条 SYSTEM）
            self._get_or_init_history(conversation_id)
            existing = self._histories[conversation_id]
        # SYSTEM prompt 已含 1 条；若超过 1 条说明已载入，直接返回
        if len(existing) > 1:
            return

        db_messages = list_messages_for_conversation(db, conversation_id)
        role_map = {
            MessageSource.USER: ChatRole.USER,
            MessageSource.ASSISTANT: ChatRole.ASSISTANT,
            MessageSource.AGENT: ChatRole.ASSISTANT,
            MessageSource.SYSTEM: ChatRole.SYSTEM,
        }
        for m in db_messages:
            role = role_map.get(m.source)
            if role is None:
                continue
            existing.append(ChatMessage(role=role, content=m.content))

    def save_messages_to_db(self, db: Session, conversation_id: int) -> list:
        """将自上次载入/保存后的「新增」user/assistant 消息回写 B2 Message 表。

        返回新增写入的 ORM Message 列表（供断言）。
        策略：
          - 查询 DB 当前已有消息数 N；SYSTEM 永远不写 DB（避免 prompt 污染对话历史）
          - 从 get_persistable_messages() 中跳过前 N 条（DB 已有的）
          - 剩余逐条调用 create_message(B2) 写入；create_message 负责 source 校验
        """
        from app.conversation.service import (
            create_message,
            list_messages_for_conversation,
        )

        existing_count = len(list_messages_for_conversation(db, conversation_id))
        persistable = self.get_persistable_messages(conversation_id)

        # 过滤 SYSTEM：SYSTEM prompt 永不入库；其余从「DB 已有 N 条」之后开始写
        non_system = [m for m in persistable if m.role != ChatRole.SYSTEM]
        to_write = non_system[existing_count:]

        written: list = []
        role_to_source = {
            ChatRole.USER: "user",
            ChatRole.ASSISTANT: "assistant",
        }
        for m in to_write:
            source = role_to_source.get(m.role)
            if source is None:
                continue
            try:
                written.append(
                    create_message(
                        db,
                        conversation_id=conversation_id,
                        source=source,
                        content=m.content,
                    )
                )
            except ValueError:
                # 非法 source：create_message 已拒绝（例如误写 TOOL → 已被
                # get_persistable_messages 过滤，这里兜底）
                continue
        if written:
            db.commit()
        return written

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _get_or_init_history(self, conversation_id: int) -> list[ChatMessage]:
        if conversation_id not in self._histories:
            self._histories[conversation_id] = [
                ChatMessage(role=ChatRole.SYSTEM, content=SYSTEM_PROMPT)
            ]
        return self._histories[conversation_id]
