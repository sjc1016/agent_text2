"""#24 UI-C-3 集成切片：WS 对话流（LLM 流式 + 消息持久化 + 多轮上下文）测试。

验收标准（issue #24 功能项）：
  - 用户与助理多轮对话，助理流式回复（信号脉冲等待首字）（US-1）
  - 通用咨询/查询在对话流返回结果（US-1, US-3~US-7, US-13）

B-2 循环 RED→GREEN：WS 消息 → AssistantService 流式接线。
  - 鉴权客户发 message → 依次收 llm.token（token 流）+ message.new(source=assistant)
  - user / assistant 消息均持久化到 Message 表（顺序 user → assistant）
  - 多轮对话：第二轮 LLM 调用能看到第一轮 user/assistant（跨轮上下文，US-1）

依赖注入：测试经 app.dependency_overrides[get_assistant_service] 注入 FakeListLLM /
历史检查 LLM 的 AssistantService（确定性；ws_client fixture 结束后统一清理）。
"""

from __future__ import annotations

import bcrypt
import pytest

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_customer(db, phone: str = "13900000050", password: str = "svc12345"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password(password))
    db.add(customer)
    db.commit()
    return customer


def _inject_assistant_service(svc) -> None:
    """注入 AssistantService 到 WS 路由依赖（ws_client fixture 结束后统一清理）。"""
    from app.main import app
    from app.ws.routes import get_assistant_service

    app.dependency_overrides[get_assistant_service] = lambda: svc


def _drain_until_assistant_reply(ws, recv_ws) -> tuple[list[str], str]:
    """消费 llm.token 流直至 message.new(source=assistant)，返回 (tokens, reply)。"""
    tokens: list[str] = []
    while True:
        ev = recv_ws(ws)
        if ev["event"] == "llm.token":
            tokens.append(ev["data"]["token"])
        elif ev["event"] == "message.new" and ev["data"]["source"] == "assistant":
            return tokens, ev["data"]["content"]


def test_ws_chat_streams_llm_tokens_then_assistant_reply(ws_client, db, recv_ws):
    """鉴权客户发消息 → 依次收 llm.token 流 + message.new(source=assistant)，且回复持久化。"""
    from sqlalchemy import select

    from app.agent.llm import FakeListLLM
    from app.agent.service import AssistantService
    from app.agent.tools import ToolRegistry
    from app.auth.security import create_access_token
    from app.models import Conversation, Message

    _inject_assistant_service(
        AssistantService(
            llm=FakeListLLM(responses=["您好，很高兴为您服务。"]),
            tool_registry=ToolRegistry(),
        )
    )

    customer = _create_customer(db, phone="13900000051")
    token = create_access_token(customer.id)
    conv = Conversation(customer_id=customer.id, status="authenticated")
    db.add(conv)
    db.commit()

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.message（accept）
        ws.send_json({"type": "message", "conversation_id": conv.id, "content": "你好"})
        tokens, reply = _drain_until_assistant_reply(ws, recv_ws)

    # llm.token：token 流拼接后等于完整回复（字符级分段，至少 2 片）
    assert reply == "您好，很高兴为您服务。"
    assert "".join(tokens) == reply
    assert len(tokens) >= 2

    # user / assistant 均已持久化（顺序 user → assistant）
    msgs = list(
        db.execute(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.id)
        ).scalars()
    )
    assert [m.source for m in msgs] == ["user", "assistant"]
    assert msgs[0].content == "你好"
    assert msgs[1].content == reply


def test_ws_chat_transaction_initiate_pushes_second_confirm(ws_client, db, recv_ws):
    """办理发起：LLM 调办理 tool → 推 second.confirm（结构化业务影响）+ 会话流转 in_progress。

    #24 验收：办理发起弹出二次确认 Modal（US-8~US-11）。
    """
    from app.agent.llm import FakeListLLM
    from app.agent.service import AssistantService
    from app.agent.tools import ToolRegistry, make_tool_call_marker
    from app.auth.security import create_access_token
    from app.models import Conversation
    from app.transaction.tools import register_transaction_tools

    registry = ToolRegistry()
    register_transaction_tools(registry)
    _inject_assistant_service(
        AssistantService(
            llm=FakeListLLM(
                responses=[
                    make_tool_call_marker("recharge", {"amount": 50}),
                    "已为您发起充值缴费申请，请确认。",
                ]
            ),
            tool_registry=registry,
        )
    )

    customer = _create_customer(db, phone="13900000053")
    token = create_access_token(customer.id)
    conv = Conversation(customer_id=customer.id, status="authenticated")
    db.add(conv)
    db.commit()

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.message（accept）
        ws.send_json({"type": "message", "conversation_id": conv.id, "content": "我要充值 50 元"})

        # 消费直至 second.confirm 到达
        confirm = None
        while confirm is None:
            ev = recv_ws(ws)
            if ev["event"] == "second.confirm":
                confirm = ev

        # 继续消费至最终 assistant 回复，确认会话状态事件（in_progress）
        got_state = None
        while True:
            ev = recv_ws(ws)
            if ev["event"] == "conversation.state":
                got_state = ev["data"]
            if ev["event"] == "message.new" and ev["data"]["source"] == "assistant":
                break

    payload = confirm["data"]
    assert payload["conversation_id"] == conv.id
    assert payload["transaction_type"] == "recharge"
    impact = payload["business_impact"]
    assert impact["summary"] == "充值缴费 50 元"
    assert impact["fee_change"] == "账户余额增加 50 元"
    assert isinstance(payload["requested_at"], str)

    # 会话已流转 in_progress（等待二次确认）
    db.refresh(conv)
    assert conv.status == "in_progress"
    # conversation.state 差量推送（authenticated → in_progress）
    assert got_state is not None
    assert got_state["old_state"] == "authenticated"
    assert got_state["new_state"] == "in_progress"


def test_ws_chat_explicit_handoff_skips_llm(ws_client, db, recv_ws):
    """显式「转人工」→ 自动触发 Handoff，不再进入 LLM 对话流。

    #24 验收：显式请求转人工触发 Handoff，Handed-off 状态（US-15, US-16）。
    事件序：system.message（转接提示）+ conversation.state（→ handed_off）+ handoff.start。
    """
    from app.agent.llm import FakeListLLM
    from app.agent.service import AssistantService
    from app.agent.tools import ToolRegistry
    from app.auth.security import create_access_token
    from app.models import Conversation

    _inject_assistant_service(
        AssistantService(
            llm=FakeListLLM(responses=["不应出现的回复"]),
            tool_registry=ToolRegistry(),
        )
    )

    customer = _create_customer(db, phone="13900000054")
    token = create_access_token(customer.id)
    conv = Conversation(customer_id=customer.id, status="authenticated")
    db.add(conv)
    db.commit()

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.message（accept）
        ws.send_json({"type": "message", "conversation_id": conv.id, "content": "我要转人工"})
        events = []
        got_handoff = False
        for _ in range(20):
            ev = recv_ws(ws)
            events.append(ev)
            if ev["event"] == "handoff.start":
                got_handoff = True
                break

    assert got_handoff
    # system.message 转接提示
    system_msgs = [e for e in events if e["event"] == "system.message"]
    assert any("转接" in e["data"]["content"] for e in system_msgs)
    # conversation.state → handed_off
    state = next(e["data"] for e in events if e["event"] == "conversation.state")
    assert state["old_state"] == "authenticated"
    assert state["new_state"] == "handed_off"
    # handoff.start reason = explicit_request
    ho = next(e["data"] for e in events if e["event"] == "handoff.start")
    assert ho["conversation_id"] == conv.id
    assert ho["reason"] == "explicit_request"
    # 不进入 LLM：无 llm.token / 无 assistant 回复
    assert not any(e["event"] == "llm.token" for e in events)
    assert not any(
        e["event"] == "message.new" and e["data"]["source"] == "assistant" for e in events
    )
    # 会话已持久化为 handed_off
    db.refresh(conv)
    assert conv.status == "handed_off"


def test_ws_chat_multiturn_preserves_history(ws_client, db, recv_ws):
    """多轮对话：第二轮 LLM 调用能看到第一轮 user/assistant（跨轮上下文，US-1）。"""
    from app.agent.llm import BaseLLM, ChatMessage, ChatRole
    from app.agent.service import AssistantService
    from app.auth.security import create_access_token
    from app.models import Conversation

    seen: list[list[ChatMessage]] = []

    class _HistoryInspectingLLM(BaseLLM):
        async def stream(self, messages):
            seen.append([ChatMessage(role=m.role, content=m.content) for m in messages])
            for ch in "收到":
                yield ch

    _inject_assistant_service(AssistantService(llm=_HistoryInspectingLLM()))

    customer = _create_customer(db, phone="13900000052")
    token = create_access_token(customer.id)
    conv = Conversation(customer_id=customer.id, status="authenticated")
    db.add(conv)
    db.commit()

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        ws.receive_json()  # system.message（accept）
        ws.send_json({"type": "message", "conversation_id": conv.id, "content": "第一轮"})
        _drain_until_assistant_reply(ws, recv_ws)
        ws.send_json({"type": "message", "conversation_id": conv.id, "content": "第二轮"})
        _drain_until_assistant_reply(ws, recv_ws)

    # 两次 LLM 调用；第二次可见 SYSTEM + USER(第一轮) + ASSISTANT(收到) + USER(第二轮)
    assert len(seen) == 2
    second = seen[1]
    assert [m.role for m in second] == [
        ChatRole.SYSTEM,
        ChatRole.USER,
        ChatRole.ASSISTANT,
        ChatRole.USER,
    ]
    assert second[1].content == "第一轮"
    assert second[3].content == "第二轮"
