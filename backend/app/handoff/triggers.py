"""Handoff 触发条件评估（纯函数，与 LLM/WS 解耦）。

PRD 依据：CONTEXT.md › 转接触发（6 类自动触发，无需用户请求）；
  issue #17 验收标准1/2（6 类条件触发 + 阈值正确触发）。

设计约定：
  - evaluate_handoff_triggers 为纯函数：给定 TriggerContext 返回 TriggerDecision，
    不读写 DB、不触达 WS——便于单元测试与后续切片（chat 集成）复用。
  - 显式条件（超出能力范围/办理失败/合规风险）无法从消息文本推断，
    由调用方经 explicit_flags 注入（如工具执行失败、意图识别器判定越界）。
  - 消息可推导条件：明确请求（关键词）、负面情绪（连续 2 轮）、
    同一意图循环（连续 3 轮，意图标签由调用方注入）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class HandoffReason(str, Enum):
    """6 类自动触发 Handoff 原因（CONTEXT › 转接触发，顺序即评估优先级）。"""

    OUT_OF_SCOPE = "out_of_scope"  # 1. 超出能力范围（v1 范围外业务）
    TRANSACTION_FAILURE = "transaction_failure"  # 2. 办理失败（入队失败/后端错误）
    EXPLICIT_REQUEST = "explicit_request"  # 3. 明确请求（用户显式说「转人工」「找客服」）
    NEGATIVE_SENTIMENT = "negative_sentiment"  # 4. 负面情绪（脏话/负面词 + 连续 2 轮）
    INTENT_LOOP = "intent_loop"  # 5. 同一意图连续 3 轮（用户反复纠正理解）
    COMPLIANCE_RISK = "compliance_risk"  # 6. 合规风险（投诉金额/违约金/合约争议）


#: 明确请求关键词（CONTEXT › 转接触发 3）。
EXPLICIT_REQUEST_KEYWORDS: tuple[str, ...] = (
    "转人工",
    "找客服",
    "人工客服",
    "转接人工",
    "人工坐席",
    "客服人员",
)

#: 负面情绪关键词（CONTEXT › 转接触发 4：脏话/负面词）。
NEGATIVE_SENTIMENT_KEYWORDS: tuple[str, ...] = (
    "投诉",
    "垃圾",
    "骗子",
    "气死",
    "混蛋",
    "太差",
    "什么态度",
    "不解决",
    "废物",
)

#: 负面情绪触发阈值：连续 2 轮（CONTEXT › 转接触发 4）。
NEGATIVE_SENTIMENT_ROUNDS = 2

#: 同一意图触发阈值：连续 3 轮（CONTEXT › 转接触发 5）。
INTENT_LOOP_ROUNDS = 3


@dataclass
class TriggerContext:
    """触发评估输入。

    last_user_messages: 最近 N 轮用户消息原文（时间正序，最老在前）；
      末尾元素为最近一轮。
    intents: 与 last_user_messages 等长的意图标签（由意图识别层注入；
      未提供或长度不匹配时降级为无法判断意图循环）。
    explicit_flags: 调用方注入的显式标记（out_of_scope / transaction_failure /
      compliance_risk 三类无法从消息文本推断的条件）。
    """

    last_user_messages: list[str] = field(default_factory=list)
    intents: list[str | None] = field(default_factory=list)
    explicit_flags: dict[HandoffReason, bool] = field(default_factory=dict)


@dataclass
class TriggerDecision:
    """评估结论：是否触发 + 触发原因（未触发时 reason/detail 为 None）。"""

    triggered: bool
    reason: HandoffReason | None = None
    detail: str | None = None


def evaluate_handoff_triggers(ctx: TriggerContext) -> TriggerDecision:
    """按 CONTEXT › 转接触发 6 类条件评估是否自动触发 Handoff。

    评估顺序与 CONTEXT 编号一致：
      1/2/6 显式注入条件 → 3 明确请求 → 4 负面情绪 → 5 同一意图循环。
    """
    for reason in (
        HandoffReason.OUT_OF_SCOPE,
        HandoffReason.TRANSACTION_FAILURE,
        HandoffReason.COMPLIANCE_RISK,
    ):
        if ctx.explicit_flags.get(reason):
            return TriggerDecision(True, reason, f"条件触发：{reason.value}")

    if ctx.last_user_messages and _contains_keyword(
        ctx.last_user_messages[-1], EXPLICIT_REQUEST_KEYWORDS
    ):
        return TriggerDecision(True, HandoffReason.EXPLICIT_REQUEST, "用户明确请求转人工")

    if _consecutive_negative_rounds(ctx) >= NEGATIVE_SENTIMENT_ROUNDS:
        return TriggerDecision(
            True,
            HandoffReason.NEGATIVE_SENTIMENT,
            f"负面情绪连续 {_consecutive_negative_rounds(ctx)} 轮",
        )

    if _consecutive_intent_rounds(ctx) >= INTENT_LOOP_ROUNDS:
        return TriggerDecision(
            True,
            HandoffReason.INTENT_LOOP,
            f"同一意图连续 {_consecutive_intent_rounds(ctx)} 轮",
        )

    return TriggerDecision(triggered=False)


def _contains_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _consecutive_negative_rounds(ctx: TriggerContext) -> int:
    """从最近一轮向前数连续命中负面关键词的轮数。"""
    count = 0
    for message in reversed(ctx.last_user_messages):
        if _contains_keyword(message, NEGATIVE_SENTIMENT_KEYWORDS):
            count += 1
        else:
            break
    return count


def _consecutive_intent_rounds(ctx: TriggerContext) -> int:
    """从最近一轮向前数同一意图标签的连续轮数。

    intents 缺失、长度不匹配或末尾意图为 None 时返回 0（无法判断）。
    """
    if not ctx.intents or len(ctx.intents) != len(ctx.last_user_messages):
        return 0
    last_intent = ctx.intents[-1]
    if last_intent is None:
        return 0
    count = 0
    for intent in reversed(ctx.intents):
        if intent == last_intent:
            count += 1
        else:
            break
    return count
