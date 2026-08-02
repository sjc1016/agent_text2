"""WebSocket 连接入口、鉴权与事件推送。

B2 循环4（issue #7 验收2）：/ws 端点，JWT 查询参数鉴权；未授权 → close code 4401。
B2 循环5（issue #7 验收3）：推送 message.new（新消息）+ system.message（系统动作）。

PRD 依据：实现决策 › API 契约 / WebSocket 事件；实现决策 › 认证与会话
  （REST 用 Authorization header，WS 用 JWT 查询参数）；测试决策 › WS 事件 seam。

鉴权校验链与 B1 REST（auth.dependencies.get_current_customer）一致：
  access type + 合法 sub + 客户存在；差异仅在取参位置与失败语义——
  WS 握手层无 HTTP 401 概念，用应用层 close code 4401 表达「未授权」
  （WebSocket close code 4000-4999 为应用自定义区间）。

事件分工（与 CONTEXT › 消息 对齐）：
  - message.new：持久化的新 Message 入对话流（四类来源均走此事件）
  - system.message：瞬时系统动作提示（不持久化为 Message，如会话建立/无权限提示）
envelope 统一为 {event, data}，payload snake_case（与 frontend/shared/events.ts 镜像）。

会话状态机 conversation.state 推送在循环6 补全。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.auth.security import decode_token, get_customer_by_id
from app.conversation.service import (
    create_message,
    get_customer_conversation_or_none,
    transition_conversation_state,
)
from app.db import get_db
from app.models import Conversation, Customer, Message
from app.ws.events import (
    ConversationStatePayload,
    MessageNewPayload,
    SystemMessagePayload,
    WsEventName,
)

router = APIRouter()

#: WS 未授权 close code（应用层自定义；HTTP 401 在 WS 握手层无对应）
_WS_UNAUTHORIZED_CODE = 4401

#: accept 后推送给客户端的会话建立提示
_SESSION_OPENED_CONTENT = "会话已建立，请问有什么可以帮您？"

DbSession = Annotated[Session, Depends(get_db)]


def resolve_ws_customer(db: Session, token: str | None) -> Customer | None:
    """解析 WS 查询参数 token → Customer；任一步失败返回 None（路由层转 close 4401）。

    校验链与 auth.dependencies.get_current_customer 一致，但失败语义改为返回 None
    而非抛 HTTPException（WS 握手层无 HTTP 401 概念）。后续切片若需统一鉴权入口，
    可抽公共「token → Customer | None」纯函数供 REST/WS 复用（重构候选）。
    """
    if not token:
        return None
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    sub = payload.get("sub")
    if not isinstance(sub, str):
        return None
    try:
        customer_id = int(sub)
    except ValueError:
        return None
    return get_customer_by_id(db, customer_id)


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
    """WS 入口：JWT 查询参数鉴权 → accept → 推会话建立 system.message → 事件收发循环。

    循环4：鉴权 + accept + 保持连接。
    循环5：accept 后推 system.message；客户端发 {type:"message",...} → 持久化 + 推 message.new。
    """
    token = websocket.query_params.get("token")
    customer = resolve_ws_customer(db, token)
    if customer is None:
        # accept 前 close：Starlette 发送 websocket.close frame，客户端收到 4401
        await websocket.close(code=_WS_UNAUTHORIZED_CODE)
        return

    await websocket.accept()
    # 系统动作：会话建立提示（不持久化为 Message）
    await _push_system_message(websocket, _SESSION_OPENED_CONTENT)

    try:
        while True:
            raw = await websocket.receive_text()
            await _handle_inbound(websocket, db, customer, raw)
    except WebSocketDisconnect:
        return


async def _handle_inbound(websocket: WebSocket, db: Session, customer: Customer, raw: str) -> None:
    """处理入站消息：解析 JSON → 按类型分发。

    循环5 处理 type=message；循环6 处理 type=state_transition；
    非法 JSON / 未知 type 暂忽略（后续切片补错误反馈）。
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict):
        return

    msg_type = data.get("type")
    if msg_type == "message":
        await _handle_client_message(websocket, db, customer, data)
    elif msg_type == "state_transition":
        await _handle_state_transition(websocket, db, customer, data)


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
