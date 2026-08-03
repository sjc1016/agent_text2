"""B8 循环1：Handoff 6 类自动触发条件评估（纯函数，unit seam）。

验收标准（issue #17）：
  6 类条件触发 Handoff（超出能力范围/办理失败/明确请求/负面情绪/同一意图循环 3 轮/合规风险）
  （PRD 依据：CONTEXT.md › 转接触发；用户故事 US-15, US-16）
  同一意图连续 3 轮、负面情绪连续 2 轮等阈值正确触发
  （PRD 依据：CONTEXT.md › 转接触发）

设计约定：评估为纯函数（evaluate_handoff_triggers），与 LLM/WS 解耦——
  显式条件（超出能力范围/办理失败/合规风险）由调用方注入 explicit_flags，
  消息可推导条件（明确请求/负面情绪/意图循环）从最近用户消息与意图标签推导。
"""

from app.handoff.triggers import (
    EXPLICIT_REQUEST_KEYWORDS,
    HandoffReason,
    TriggerContext,
    evaluate_handoff_triggers,
)


def _ctx(last_messages=None, intents=None, explicit=None) -> TriggerContext:
    return TriggerContext(
        last_user_messages=list(last_messages or []),
        intents=list(intents or []),
        explicit_flags=dict(explicit or {}),
    )


class TestExplicitTriggers:
    """1/2/6：超出能力范围 / 办理失败 / 合规风险（调用方注入显式标记）。"""

    def test_out_of_scope_triggers(self):
        decision = evaluate_handoff_triggers(
            _ctx(last_messages=["帮我销户"], explicit={HandoffReason.OUT_OF_SCOPE: True})
        )
        assert decision.triggered
        assert decision.reason == HandoffReason.OUT_OF_SCOPE
        assert decision.detail

    def test_transaction_failure_triggers(self):
        decision = evaluate_handoff_triggers(
            _ctx(last_messages=["充值"], explicit={HandoffReason.TRANSACTION_FAILURE: True})
        )
        assert decision.triggered
        assert decision.reason == HandoffReason.TRANSACTION_FAILURE

    def test_compliance_risk_triggers(self):
        decision = evaluate_handoff_triggers(
            _ctx(last_messages=["违约金争议"], explicit={HandoffReason.COMPLIANCE_RISK: True})
        )
        assert decision.triggered
        assert decision.reason == HandoffReason.COMPLIANCE_RISK

    def test_explicit_flags_absent_no_trigger(self):
        decision = evaluate_handoff_triggers(_ctx(last_messages=["帮我销户"]))
        assert not decision.triggered


class TestExplicitRequest:
    """3：明确请求（用户显式说「转人工」「找客服」）。"""

    def test_each_keyword_triggers(self):
        for keyword in EXPLICIT_REQUEST_KEYWORDS:
            decision = evaluate_handoff_triggers(_ctx(last_messages=[f"请{keyword}"]))
            assert decision.triggered, f"keyword {keyword!r} should trigger"
            assert decision.reason == HandoffReason.EXPLICIT_REQUEST

    def test_normal_request_not_trigger(self):
        decision = evaluate_handoff_triggers(_ctx(last_messages=["话费余额多少"]))
        assert not decision.triggered


class TestNegativeSentiment:
    """4：负面情绪——关键词命中 + 连续 2 轮触发（CONTEXT › 转接触发 4）。"""

    def test_single_negative_round_not_trigger(self):
        decision = evaluate_handoff_triggers(_ctx(last_messages=["你们服务太差了"]))
        assert not decision.triggered

    def test_two_consecutive_negative_rounds_trigger(self):
        decision = evaluate_handoff_triggers(
            _ctx(last_messages=["什么态度", "你们就是垃圾"]),
        )
        assert decision.triggered
        assert decision.reason == HandoffReason.NEGATIVE_SENTIMENT

    def test_negative_then_normal_breaks_run(self):
        decision = evaluate_handoff_triggers(
            _ctx(last_messages=["太差了", "帮我查下话费"]),
        )
        assert not decision.triggered

    def test_three_negative_rounds_also_trigger(self):
        decision = evaluate_handoff_triggers(
            _ctx(last_messages=["不解决", "投诉你们", "气死我了"]),
        )
        assert decision.triggered
        assert decision.reason == HandoffReason.NEGATIVE_SENTIMENT


class TestIntentLoop:
    """5：同一意图连续 3 轮触发（CONTEXT › 转接触发 5）。"""

    def test_three_same_intent_rounds_trigger(self):
        decision = evaluate_handoff_triggers(
            _ctx(
                last_messages=["转套餐", "我说的是转套餐", "你到底懂不懂转套餐"],
                intents=["plan_change", "plan_change", "plan_change"],
            )
        )
        assert decision.triggered
        assert decision.reason == HandoffReason.INTENT_LOOP

    def test_two_same_intent_rounds_not_trigger(self):
        decision = evaluate_handoff_triggers(
            _ctx(
                last_messages=["转套餐", "对，转套餐"],
                intents=["plan_change", "plan_change"],
            )
        )
        assert not decision.triggered

    def test_three_mixed_intent_rounds_not_trigger(self):
        decision = evaluate_handoff_triggers(
            _ctx(
                last_messages=["查话费", "转套餐", "确认转套餐"],
                intents=["inquiry_balance", "plan_change", "plan_change"],
            )
        )
        assert not decision.triggered

    def test_missing_intents_no_trigger(self):
        decision = evaluate_handoff_triggers(
            _ctx(last_messages=["转套餐", "转套餐", "转套餐"]),
        )
        assert not decision.triggered


class TestNoTrigger:
    """正常对话（无 6 类条件命中）不触发。"""

    def test_normal_conversation_no_trigger(self):
        decision = evaluate_handoff_triggers(
            _ctx(last_messages=["你好", "查一下话费", "谢谢"]),
        )
        assert not decision.triggered
        assert decision.reason is None
        assert decision.detail is None
