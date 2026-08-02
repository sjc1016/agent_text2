"""WS 连接注册表与跨请求推送（hub）。

B7（issue #10 验收4）：REST 状态流转（PATCH /tickets/{id}）需向所属客户推送
WS ticket.update / notification.push —— 推送方不在 WS 连接上下文内，故引入
按 customer_id 维护活跃连接的注册表，供 REST / 调度等跨请求推送复用。

设计约定：
  - hub 为模块级单例（单进程 uvicorn 部署，PRD › 部署）。
  - ws/routes.py 在 accept 后注册、WebSocketDisconnect 后注销。
  - push_ticket_update / push_notification 供业务路由在 db.commit 后调用；
    未连接该客户时静默跳过（推送非业务主路径，不抛错）。
  - envelope 仍为 {event, data}，payload snake_case（与 frontend/shared/events.ts 镜像）。
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from app.models import Notification, Ticket, User
from app.ws.events import (
    AgentStatusPayload,
    NotificationPushPayload,
    TicketUpdatePayload,
    WsEventName,
)

logger = logging.getLogger(__name__)


class ConnectionHub:
    """按 customer_id / agent_id 维护活跃 WS 连接，支持向指定主体推送事件。

    B7 引入客户侧（ticket.update / notification.push）；B9 扩展坐席侧
    （agent.status）—— 两套注册表独立键控，避免主体 ID 空间冲突
    （customers.id 与 users.id 各自自增）。
    """

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)
        self._agent_connections: dict[int, set[WebSocket]] = defaultdict(set)

    def reset(self) -> None:
        """清空全部连接注册表（测试隔离用：模块级单例跨测试残留会污染推送）。"""
        self._connections.clear()
        self._agent_connections.clear()

    def connect(self, customer_id: int, websocket: WebSocket) -> None:
        """注册客户连接（accept 后调用）。"""
        self._connections[customer_id].add(websocket)

    def disconnect(self, customer_id: int, websocket: WebSocket) -> None:
        """注销客户连接（断开后调用）。"""
        connections = self._connections.get(customer_id)
        if connections is None:
            return
        connections.discard(websocket)
        if not connections:
            self._connections.pop(customer_id, None)

    def connect_agent(self, agent_id: int, websocket: WebSocket) -> None:
        """注册坐席连接（accept 后调用）。"""
        self._agent_connections[agent_id].add(websocket)

    def disconnect_agent(self, agent_id: int, websocket: WebSocket) -> None:
        """注销坐席连接（断开后调用）。"""
        connections = self._agent_connections.get(agent_id)
        if connections is None:
            return
        connections.discard(websocket)
        if not connections:
            self._agent_connections.pop(agent_id, None)

    async def push_to_customer(
        self, customer_id: int, event: WsEventName, data: dict[str, Any]
    ) -> None:
        """向该客户全部活跃连接推送 {event, data}；无连接时静默跳过。"""
        connections = self._connections.get(customer_id)
        if not connections:
            return
        for ws in list(connections):
            try:
                await ws.send_json({"event": event.value, "data": data})
            except Exception:  # noqa: BLE001 - 推送失败不阻断业务主路径
                logger.warning("ws push failed", exc_info=True)

    async def push_to_agent(self, agent_id: int, event: WsEventName, data: dict[str, Any]) -> None:
        """向该坐席全部活跃连接推送 {event, data}；无连接时静默跳过。"""
        connections = self._agent_connections.get(agent_id)
        if not connections:
            return
        for ws in list(connections):
            try:
                await ws.send_json({"event": event.value, "data": data})
            except Exception:  # noqa: BLE001 - 推送失败不阻断业务主路径
                logger.warning("ws push failed", exc_info=True)


#: 模块级单例（单进程部署）。
hub = ConnectionHub()


async def push_ticket_update(ticket: Ticket, old_status: str) -> None:
    """推送 ticket.update（工单状态变化，PRD line 282）。"""
    if ticket.customer_id is None:
        return  # Visitor 工单无客户目标（坐席/后续切片另行通知）
    payload = TicketUpdatePayload(
        id=ticket.id,
        conversation_id=ticket.conversation_id,
        ticket_type=ticket.ticket_type.value,
        status=ticket.status.value,
        old_status=old_status,
        changed_at=datetime.now(timezone.utc),
    ).model_dump(mode="json")
    await hub.push_to_customer(ticket.customer_id, WsEventName.TICKET_UPDATE, payload)


async def push_notification(notification: Notification) -> None:
    """推送 notification.push（站内通知，PRD line 282）。"""
    if notification.customer_id is None:
        return  # Visitor 场景无推送目标
    payload = NotificationPushPayload(
        id=notification.id,
        ticket_id=notification.ticket_id,
        message=notification.message,
        read=notification.read,
        created_at=notification.created_at,
    ).model_dump(mode="json")
    await hub.push_to_customer(notification.customer_id, WsEventName.NOTIFICATION_PUSH, payload)


async def push_agent_status(agent: User, status: str) -> None:
    """推送 agent.status（坐席状态变更，PRD line 282；US-30）。

    REST PUT /agents/status 在 db.commit 后调用；该坐席未连接 WS 时静默跳过
    （推送非业务主路径，不抛错）。
    """
    payload = AgentStatusPayload(
        agent_id=agent.id,
        status=status,
        changed_at=datetime.now(timezone.utc),
    ).model_dump(mode="json")
    await hub.push_to_agent(agent.id, WsEventName.AGENT_STATUS, payload)
