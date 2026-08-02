"""WebSocket 连接入口、鉴权与事件推送。

B2 循环4（issue #7 验收2）：/ws 端点，JWT 查询参数鉴权；未授权 → close code 4401。
B2 循环5（issue #7 验收3）：推送 message.new（新消息）+ system.message（系统动作）。

PRD 依据：实现决策 › API 契约 / WebSocket 事件；实现决策 › 认证与会话
  （REST 用 Authorization header，WS 用 JWT 查询参数）；测试决策 › WS 事件 seam。

鉴权校验链与 B1 REST（auth.dependencies）一致：
  access type + 合法 sub + 主体存在；差异仅在取参位置与失败语义——
  WS 握手层无 HTTP 401 概念，用应用层 close code 4401 表达「未授权」
  （WebSocket close code 4000-4999 为应用自定义区间）。

主体双轨（B9，issue #15）：
  - type=access 的客户 token → customer 连接（客户发消息 / 状态流转）
  - type=agent_access 的坐席 token → agent 连接（接入/发坐席消息/转回助理）
  两类主体连接均注册到 hub（B7 客户侧 / B9 坐席侧），供跨请求推送。

事件分工（与 CONTEXT › 消息 对齐）：
  - message.new：持久化的新 Message 入对话流（四类来源均走此事件）
  - system.message：瞬时系统动作提示（不持久化为 Message，如会话建立/无权限提示）
envelope 统一为 {event, data}，payload snake_case（与 frontend/shared/events.ts 镜像）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.auth.security import decode_token, get_agent_by_id, get_customer_by_id
from app.conversation.service import (
    create_message,
    get_customer_conversation_or_none,
    transition_conversation_state,
)
from app.db import get_db
from app.models import Conversation, Customer, Message, User
from app.ws.events import (
    ConversationStatePayload,
    MessageNewPayload,
    SystemMessagePayload,
    WsEventName,
)
from app.ws.hub import hub

router = APIRouter()

#: WS 未授权 close code（应用层自定义；HTTP 401 在 WS 握手层无对应）
_WS_UNAUTHORIZED_CODE = 4401

#: accept 后推送给客户端/坐席的会话建立提示
_SESSION_OPENED_CONTENT = "会话已建立，请问有什么可以帮您？"
_AGENT_SESSION_OPENED_CONTENT = "坐席工作台已连接"

DbSession = Annotated[Session, Depends(get_db)]


@dataclass
class WsIdentity:
    """WS 连接身份：kind ∈ customer/agent，subject 为对应主体 ORM。

    REST 侧主体隔离（get_current_customer / get_current_agent）在 WS 侧
    以 kind 区分；两类连接的事件处理分支由 kind 路由（_handle_inbound）。
    """

    kind: str
    subject: Customer | User


def resolve_ws_identity(db: Session, token: str | None) -> WsIdentity | None:
    """解析 WS 查询参数 token → WsIdentity；任一步失败返回 None（路由层转 close 4401）。

    校验链与 auth.dependencies 一致（access / agent_access type + 合法 sub +
    主体存在），但失败语义改为返回 None（WS 握手层无 HTTP 401 概念）。
    """
    if not token:
        return None
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        return None

    token_type = payload.get("type")
    sub = payload.get("sub")
    if not isinstance(sub, str):
        return None
    try:
        subject_id = int(sub)
    except ValueError:
        return None

    if token_type == "access":
        customer = get_customer_by_id(db, subject_id)
        if customer is None:
            return None
        return WsIdentity(kind="customer", subject=customer)
    if token_type == "agent_access":
        agent = get_agent_by_id(db, subject_id)
        if agent is None:
            return None
        return WsIdentity(kind="agent", subject=agent)
    return None


async def _send_event(websocket: WebSocket, event: WsEventName, data: dict[str, Any]) -> None:
    """发送 {event, data} envelope；data 已序列化为 JSON 兼容字典。"""
    await websocket.send_json({"event": event.value, "data": data})


async def _push_message_new(websocket: WebSocket, message: Message) -> None:
    """推送 message.new 事件，payload 与 REST MessageOut 字段镜像。"""
    payload = MessageNewPayload.model_validate(message).model_dump(mode="json")
    await _send_event(websocket, WsEventName.MESSAGE_NEW, payload)


async def _push_system_message(websocket: WebSocket, content: str) -> None:
    """推送 system.message 事件（瞬时系统动作提示，不持久化）。"""
    payload = SystemMessagePayload(
        content=content, created_at=datetime.now(timezone.utc)
    ).model_dump(mode="json")
    await _send_event(websocket, WsEventName.SYSTEM_MESSAGE, payload)


async def _push_conversation_state(
    websocket: WebSocket, conv: Conversation, old_state: str
) -> None:
    """推送 conversation.state 事件（状态机流转通知，PRD line 286）。"""
    payload = ConversationStatePayload(
        conversation_id=conv.id,
        old_state=old_state,
        new_state=conv.status,
        changed_at=datetime.now(timezone.utc),
    ).model_dump(mode="json")
    await _send_event(websocket, WsEventName.CONVERSATION_STATE, payload)


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket, db: DbSession) -> None:
    """WS 入口：JWT 查询参数鉴权 → accept → 推建立提示 system.message → 事件收发循环。

    客户连接：accept 后推「会话已建立」+ hub 注册（B7 客户侧推送）。
    坐席连接：accept 后推「坐席工作台已连接」+ hub 坐席侧注册（B9 agent.status 推送）。
    未授权（无 token / 非法 / 主体不存在）→ close code 4401。
    """
    token = websocket.query_params.get("token")
    identity = resolve_ws_identity(db, token)
    if identity is None:
        # accept 前 close：Starlette 发送 websocket.close frame，客户端收到 4401
        await websocket.close(code=_WS_UNAUTHORIZED_CODE)
        return

    await websocket.accept()
    if identity.kind == "agent":
        hub.connect_agent(identity.subject.id, websocket)
        await _push_system_message(websocket, _AGENT_SESSION_OPENED_CONTENT)
    else:
        # 注册连接：供 REST/调度跨请求推送 ticket.update / notification.push（B7 hub）
        hub.connect(identity.subject.id, websocket)
        # 系统动作：会话建立提示（不持久化为 Message）
        await _push_system_message(websocket, _SESSION_OPENED_CONTENT)

    try:
        while True:
            raw = await websocket.receive_text()
            await _handle_inbound(websocket, db, identity, raw)
    except WebSocketDisconnect:
        pass
    finally:
        if identity.kind == "agent":
            hub.disconnect_agent(identity.subject.id, websocket)
        else:
            hub.disconnect(identity.subject.id, websocket)


async def _handle_inbound(
    websocket: WebSocket, db: Session, identity: WsIdentity, raw: str
) -> None:
    """处理入站消息：解析 JSON → 按身份与类型分发。

    客户（kind=customer）：message / state_transition（B2）。
    坐席（kind=agent）：message（坐席消息）/ take_over（接入）/ state_transition（转回）。
    非法 JSON / 未知 type 暂忽略（后续切片补错误反馈）。
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict):
        return

    if identity.kind == "agent":
        subject = identity.subject
        assert isinstance(subject, User), "agent 身份主体必须是 User"
        await _handle_agent_inbound(websocket, db, subject, data)
        return

    subject = identity.subject
    assert isinstance(subject, Customer), "customer 身份主体必须是 Customer"
    msg_type = data.get("type")
    if msg_type == "message":
        await _handle_client_message(websocket, db, subject, data)
    elif msg_type == "state_transition":
        await _handle_state_transition(websocket, db, subject, data)


async def _handle_agent_inbound(
    websocket: WebSocket, db: Session, agent: User, data: dict[str, Any]
) -> None:
    """坐席连接入站分发：接入会话 / 发坐席消息 / 转回助理。"""
    msg_type = data.get("type")
    if msg_type == "take_over":
        await _handle_agent_take_over(websocket, db, agent, data)
    elif msg_type == "message":
        await _handle_agent_message(websocket, db, agent, data)
    elif msg_type == "state_transition":
        await _handle_agent_transfer_back(websocket, db, agent, data)


async def _handle_agent_take_over(
    websocket: WebSocket, db: Session, agent: User, data: dict[str, Any]
) -> None:
    """坐席接入转接会话（US-21）：校验 handed_off 未接入 → 绑定 agent_id。

    成功：坐席收 system.message 确认；客户收 system.message「人工客服已接入」
    （用户视角「客服」）；写审计 agent.take_over。
    不可接入（不存在/非 handed_off/已被他人接入）→ 坐席收 system.message 提示，
    会话不变更。
    """
    from app.auth.audit import write_audit_log

    conversation_id = data.get("conversation_id")
    if not isinstance(conversation_id, int):
        return

    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.status != "handed_off" or conv.agent_id is not None:
        await _push_system_message(websocket, "该会话不可接入（不存在/非转接中/已被接入）")
        return

    conv.agent_id = agent.id
    write_audit_log(
        db,
        actor_type="agent",
        actor_id=agent.id,
        action="agent.take_over",
        detail={"conversation_id": conv.id},
    )
    db.refresh(conv)
    await _push_system_message(websocket, f"已接入会话 #{conv.id}，可开始对话")
    if conv.customer_id is not None:
        payload = SystemMessagePayload(
            content="人工客服已接入，为您服务",
            created_at=datetime.now(timezone.utc),
        ).model_dump(mode="json")
        await hub.push_to_customer(conv.customer_id, WsEventName.SYSTEM_MESSAGE, payload)


async def _handle_agent_message(
    websocket: WebSocket, db: Session, agent: User, data: dict[str, Any]
) -> None:
    """坐席发消息（US-21）：仅已接入该会话的坐席可发，持久化 source=agent 消息。

    成功：推 message.new 给坐席连接与客户连接（用户视角「客服」消息）。
    未接入/已被转回（agent_id 非本坐席）→ 坐席收 system.message 提示，
    不持久化、不推送（与客户侧无权限边界一致）。
    """
    conversation_id = data.get("conversation_id")
    content = data.get("content")
    if not isinstance(conversation_id, int) or not isinstance(content, str) or not content:
        return

    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.agent_id != agent.id:
        await _push_system_message(websocket, "无权在该会话发言（未接入或已转回助理）")
        return

    message = create_message(db, conv.id, "agent", content)
    db.commit()
    db.refresh(message)
    payload = MessageNewPayload.model_validate(message).model_dump(mode="json")
    await _send_event(websocket, WsEventName.MESSAGE_NEW, payload)
    if conv.customer_id is not None:
        await hub.push_to_customer(conv.customer_id, WsEventName.MESSAGE_NEW, payload)


async def _handle_agent_transfer_back(
    websocket: WebSocket, db: Session, agent: User, data: dict[str, Any]
) -> None:
    """坐席转回助理（US-26）：会话状态 handed_off → authenticated，agent_id 置空。

    成功：坐席收 system.message 确认；客户收 conversation.state + system.message
    （已转回智能助理）；写审计 agent.transfer_back。
    非法（未接入/非 handed_off）→ 坐席收 system.message 提示，状态不变更。
    """
    from app.auth.audit import write_audit_log

    conversation_id = data.get("conversation_id")
    if not isinstance(conversation_id, int):
        return

    conv = db.get(Conversation, conversation_id)
    if conv is None or conv.agent_id != agent.id:
        await _push_system_message(websocket, "无权操作该会话（未接入）")
        return

    old_state = conv.status
    if conv.status != "handed_off":
        await _push_system_message(websocket, f"会话状态 {conv.status!r} 不可转回")
        return

    try:
        transition_conversation_state(db, conv, "authenticated")
    except ValueError as exc:
        await _push_system_message(websocket, f"状态流转失败：{exc}")
        return

    conv.agent_id = None
    write_audit_log(
        db,
        actor_type="agent",
        actor_id=agent.id,
        action="agent.transfer_back",
        detail={"conversation_id": conv.id},
    )
    db.refresh(conv)
    await _push_system_message(websocket, f"会话 #{conv.id} 已转回智能助理")
    await _push_conversation_state(websocket, conv, old_state)
    if conv.customer_id is not None:
        state_payload = ConversationStatePayload(
            conversation_id=conv.id,
            old_state=old_state,
            new_state=conv.status,
            changed_at=datetime.now(timezone.utc),
        ).model_dump(mode="json")
        await hub.push_to_customer(conv.customer_id, WsEventName.CONVERSATION_STATE, state_payload)
        hint = SystemMessagePayload(
            content="会话已转回智能助理，继续为您服务",
            created_at=datetime.now(timezone.utc),
        ).model_dump(mode="json")
        await hub.push_to_customer(conv.customer_id, WsEventName.SYSTEM_MESSAGE, hint)


async def _handle_client_message(
    websocket: WebSocket, db: Session, customer: Customer, data: dict[str, Any]
) -> None:
    """处理客户端发消息：校验会话归属 → 持久化 user 消息 → 推 message.new。

    会话不属于当前客户 → 推 system.message 无权限提示（不泄露他人会话存在性，
    与 REST list_messages 边界一致）；不持久化、不推 message.new。
    """
    conversation_id = data.get("conversation_id")
    content = data.get("content")
    if not isinstance(conversation_id, int) or not isinstance(content, str) or not content:
        return

    conv = get_customer_conversation_or_none(db, customer, conversation_id)
    if conv is None:
        await _push_system_message(websocket, "无权操作该会话")
        return

    message = create_message(db, conv.id, "user", content)
    db.commit()
    await _push_message_new(websocket, message)


async def _handle_state_transition(
    websocket: WebSocket, db: Session, customer: Customer, data: dict[str, Any]
) -> None:
    """处理客户端状态流转请求：校验会话归属 → 状态机校验 → 推 conversation.state。

    循环6 以客户端 state_transition 消息模拟业务事件触发，验证推送机制 + 状态机；
    后续切片（handoff / ticket 入队等）会以真实业务事件驱动 transition，
    复用本服务的 transition_conversation_state + _push_conversation_state。

    会话不属于当前客户 → system.message 无权限提示。
    非法状态转换 / 未知状态 / 同态 → system.message 错误提示，状态不变更。
    """
    conversation_id = data.get("conversation_id")
    new_state = data.get("new_state")
    if not isinstance(conversation_id, int) or not isinstance(new_state, str):
        return

    conv = get_customer_conversation_or_none(db, customer, conversation_id)
    if conv is None:
        await _push_system_message(websocket, "无权操作该会话")
        return

    old_state = conv.status
    try:
        transition_conversation_state(db, conv, new_state)
    except ValueError as exc:
        await _push_system_message(websocket, f"状态流转失败：{exc}")
        return

    db.commit()
    await _push_conversation_state(websocket, conv, old_state)
