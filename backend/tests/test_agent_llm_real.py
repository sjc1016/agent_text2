"""B3 真实 LLM 接入：OpenAICompatLLM（OpenAI 兼容 /chat/completions）。

PRD 依据：B3（issue #9）BaseLLM seam——真实 provider 与 FakeListLLM 实现同一
接口，接口不变仅换 provider。测试用 httpx.MockTransport 拦截请求（确定性、无
网络、CI 可跑），覆盖：
  - 非流式 invoke：请求 URL / 认证头 / body（模型、协议提示、消息翻译）+ 返回解析
  - 流式 stream：SSE delta 逐段产出 + [DONE] 终止
  - TOOL role 消息翻译为 user role（工具结果前缀标记）
  - 工具清单 tool_descriptions 注入 system 消息
  - 非 200 状态抛错（错误对调用方可见而非静默空流）
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.agent.llm import BaseLLM, ChatMessage, ChatRole, FailoverLLM, OpenAICompatLLM
from app.agent.service import AssistantService


class _AlwaysFailLLM(BaseLLM):
    """LLM 调用即抛错（模拟 provider 不可用）。"""

    def __init__(self, name: str) -> None:
        self._name = name

    def invoke(self, messages: list[ChatMessage]) -> str:
        raise RuntimeError(f"{self._name} failed")

    def stream(self, messages: list[ChatMessage]):
        raise RuntimeError(f"{self._name} failed")
        yield  # pragma: no cover - 不可达


class _FixedLLM(BaseLLM):
    """LLM 固定返回文本（确定性 fake）。"""

    def __init__(self, name: str, text: str) -> None:
        self._name = name
        self._text = text

    def invoke(self, messages: list[ChatMessage]) -> str:
        return self._text

    def stream(self, messages: list[ChatMessage]):
        yield from self._text


class _RaisingLLM(BaseLLM):
    """LLM 流式调用即抛错（模拟 provider 过载 / 超时）。"""

    def stream(self, messages: list[ChatMessage]):
        raise RuntimeError("HTTP 529 Service temporarily overloaded")
        yield  # pragma: no cover - 不可达


def _make_llm(handler) -> OpenAICompatLLM:
    """构造绑定 MockTransport 的 OpenAICompatLLM（不触发真实网络）。"""
    return OpenAICompatLLM(
        base_url="https://example.com/v1",
        api_key="test-key",
        model="test-model",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_invoke_builds_request_and_returns_content():
    """invoke：请求 URL/头/body 正确，choices[0].message.content 作为返回。"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "你好，电信客服。"}}]},
        )

    llm = _make_llm(handler)
    result = llm.invoke([ChatMessage(role=ChatRole.USER, content="查一下话费")])

    assert captured["url"] == "https://example.com/v1/chat/completions"
    assert captured["auth"] == "Bearer test-key"
    body = captured["body"]
    assert body["model"] == "test-model"
    assert body["stream"] is False
    # 首条 system = 工具调用协议提示（独立注入，不改 SYSTEM_PROMPT）
    assert body["messages"][0]["role"] == "system"
    assert "工具调用协议" in body["messages"][0]["content"]
    # 领域消息翻译为 OpenAI 消息
    assert body["messages"][-1] == {"role": "user", "content": "查一下话费"}
    assert result == "你好，电信客服。"


def test_stream_yields_sse_deltas():
    """stream：SSE `data:` 行逐段产出 delta.content，遇 [DONE] 终止。"""
    sse = (
        'data: {"choices":[{"delta":{"role":"assistant","content":"你"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"好"}}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, text=sse)

    llm = _make_llm(handler)
    tokens = list(llm.stream([ChatMessage(role=ChatRole.USER, content="hi")]))
    assert tokens == ["你", "好"]


def test_tool_message_translated_to_user_role_with_label():
    """TOOL role（工具执行结果）→ user role 消息，前缀标记工具名（v1 协议）。"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    llm = _make_llm(handler)
    history = [
        ChatMessage(role=ChatRole.USER, content="查话费"),
        ChatMessage(
            role=ChatRole.TOOL,
            content="当前话费余额为 58.20 元。",
            tool_call_id="call_1",
            tool_name="get_balance",
        ),
    ]
    llm.invoke(history)

    assert captured["body"]["messages"][-1] == {
        "role": "user",
        "content": "[工具 get_balance 结果] 当前话费余额为 58.20 元。",
    }


def test_tool_descriptions_injected_as_system_message():
    """tool_descriptions（工具清单）注入请求体 system 消息，供模型选工具。"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": ""}}]})

    llm = OpenAICompatLLM(
        base_url="https://example.com/v1",
        api_key="k",
        model="m",
        tool_descriptions="- get_balance: 查询话费余额",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    llm.invoke([ChatMessage(role=ChatRole.USER, content="hi")])

    system_contents = [m["content"] for m in captured["body"]["messages"] if m["role"] == "system"]
    assert any("可用工具" in c and "get_balance" in c for c in system_contents)


def test_stream_raises_on_non_200():
    """非 200：流式调用抛 RuntimeError（错误可见，而非静默空流）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid api key")

    llm = _make_llm(handler)
    try:
        list(llm.stream([ChatMessage(role=ChatRole.USER, content="hi")]))
        raise AssertionError("应抛出 RuntimeError")
    except RuntimeError as e:
        assert "HTTP 401" in str(e)


@pytest.mark.anyio
async def test_chat_falls_back_when_llm_stream_raises():
    """LLM provider 抛错（如 529 过载）→ chat() 兜底提示话术，而非抛错中断连接。"""
    svc = AssistantService(llm=_RaisingLLM())
    tokens: list[str] = []
    async for tok in svc.chat(conversation_id=1, user_message="查话费"):
        tokens.append(tok)

    assert "".join(tokens) == "抱歉，当前服务繁忙，请稍后重试。"
    # 兜底话术入历史（行为可观察：后续轮次仍可继续对话）
    history = svc.get_history(conversation_id=1)
    assert history[-1].role == ChatRole.ASSISTANT
    assert history[-1].content == "抱歉，当前服务繁忙，请稍后重试。"


# ---------------------------------------------------------------------------
# FailoverLLM：主备自动切换
# ---------------------------------------------------------------------------


def test_failover_switches_to_backup_when_primary_fails():
    """主 provider 失败 → invoke / stream 均自动切换到备 provider。"""
    llm = FailoverLLM(providers=[_AlwaysFailLLM("primary"), _FixedLLM("backup", "备用回复")])
    messages = [ChatMessage(role=ChatRole.USER, content="查话费")]

    assert llm.invoke(messages) == "备用回复"
    assert "".join(llm.stream(messages)) == "备用回复"


def test_failover_uses_primary_when_healthy():
    """主 provider 正常 → 备 provider 不被调用。"""
    llm = FailoverLLM(providers=[_FixedLLM("primary", "主回复"), _AlwaysFailLLM("backup")])
    messages = [ChatMessage(role=ChatRole.USER, content="查话费")]

    assert llm.invoke(messages) == "主回复"
    assert "".join(llm.stream(messages)) == "主回复"


def test_failover_all_fail_raises_last_error():
    """全部 provider 失败 → 抛出最后一个异常（由 chat() 兜底话术降级）。"""
    llm = FailoverLLM(providers=[_AlwaysFailLLM("a"), _AlwaysFailLLM("b")])
    messages = [ChatMessage(role=ChatRole.USER, content="查话费")]

    with pytest.raises(RuntimeError, match="b failed"):
        llm.invoke(messages)
    with pytest.raises(RuntimeError, match="b failed"):
        list(llm.stream(messages))


def test_failover_empty_providers_rejected():
    """providers 为空 → 构造时报错（避免静默降级为空回复）。"""
    with pytest.raises(ValueError, match="不能为空"):
        FailoverLLM(providers=[])


def test_invoke_with_full_path_base_url_does_not_duplicate_path():
    """base_url 已含 /chat/completions（如 agnes-ai）→ 不重复拼接路径。"""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    llm = OpenAICompatLLM(
        base_url="https://apihub.agnes-ai.com/v1/chat/completions",
        api_key="k",
        model="m",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    llm.invoke([ChatMessage(role=ChatRole.USER, content="hi")])
    assert captured["url"] == "https://apihub.agnes-ai.com/v1/chat/completions"


def test_default_service_builds_failover_when_both_keys(monkeypatch):
    """主备 key 均配置 → 默认服务用 FailoverLLM（2 个 provider）。"""
    from app.config import get_settings
    from app.ws.routes import _build_default_assistant_service

    get_settings.cache_clear()
    try:
        monkeypatch.setenv("APP_LLM_API_KEY", "primary-key")
        monkeypatch.setenv("APP_LLM_FAILOVER_API_KEY", "failover-key")
        svc = _build_default_assistant_service()
        assert isinstance(svc.llm, FailoverLLM)
        assert len(svc.llm._providers) == 2
    finally:
        get_settings.cache_clear()


def test_default_service_single_provider_without_failover_key(monkeypatch):
    """仅配置主 key → 默认服务直接用 OpenAICompatLLM（不包 FailoverLLM）。"""
    from app.config import get_settings
    from app.ws.routes import _build_default_assistant_service

    get_settings.cache_clear()
    try:
        monkeypatch.setenv("APP_LLM_API_KEY", "primary-key")
        monkeypatch.setenv("APP_LLM_FAILOVER_API_KEY", "")  # 空 → 无备
        svc = _build_default_assistant_service()
        assert isinstance(svc.llm, OpenAICompatLLM)
    finally:
        get_settings.cache_clear()
