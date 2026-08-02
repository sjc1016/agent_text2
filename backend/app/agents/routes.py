"""坐席 REST 路由（/agents/login、/agents/status、/agents/queues）。

B9（issue #15）：
  POST /agents/login  — 工号+密码登录，颁发坐席 JWT（US-19）
  PUT  /agents/status — 切换在线/离线/小休（US-30；WS agent.status 推送走 WS seam）
  GET  /agents/queues — 待接入 Handoff 会话列表（US-20）

PRD 依据：实现决策 › API 契约 /agents/*；测试决策 › HTTP 集成 seam。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agents.schemas import (
    AgentLoginRequest,
    AgentPublic,
    AgentStatusUpdate,
    QueueItemOut,
)
from app.agents.service import authenticate_agent, list_pending_queue_entries
from app.auth.audit import write_audit_log
from app.auth.dependencies import CurrentAgent
from app.auth.schemas import TokenResponse
from app.auth.security import create_agent_access_token, create_agent_refresh_token
from app.db import get_db
from app.models import User
from app.ws.hub import push_agent_status

router = APIRouter(prefix="/agents", tags=["agents"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post("/login", response_model=TokenResponse)
def agent_login(payload: AgentLoginRequest, db: DbSession) -> TokenResponse:
    """工号+密码登录 → 颁发坐席 JWT；成功/失败均记审计（CONTEXT › 审计日志）。"""
    agent = authenticate_agent(db, payload.employee_id, payload.password)
    if agent is None:
        write_audit_log(
            db,
            actor_type="agent",
            action="agent.login.failure",
            detail={"employee_id": payload.employee_id},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="工号或密码错误",
        )
    write_audit_log(
        db,
        actor_type="agent",
        actor_id=agent.id,
        action="agent.login.success",
    )
    return TokenResponse(
        access_token=create_agent_access_token(agent.id),
        refresh_token=create_agent_refresh_token(agent.id),
    )


@router.put("/status", response_model=AgentPublic)
async def update_agent_status(
    payload: AgentStatusUpdate, db: DbSession, current: CurrentAgent
) -> User:
    """切换坐席状态（在线/离线/小休，US-30）。

    坐席 JWT 保护（CurrentAgent）；非法状态由 schema Literal 转 422。
    db.commit 后经 hub 向该坐席活跃 WS 连接推送 agent.status
    （REST 与 WS 独立连接，推送方不在 WS 上下文内 —— 复用 B7 hub 模式）。
    """
    current.status = payload.status
    db.commit()
    db.refresh(current)
    await push_agent_status(current, payload.status)
    return current


@router.get("/queues", response_model=list[QueueItemOut])
def list_pending_queues(db: DbSession, current: CurrentAgent) -> list[QueueItemOut]:
    """待接入 Handoff 会话列表（US-20）。

    仅返回 handed_off 且未被接入的会话；号码脱敏（138****0001）。
    """
    return [
        QueueItemOut(
            conversation_id=entry.conversation.id,
            status=entry.conversation.status,
            created_at=entry.conversation.created_at,
            customer_id=entry.conversation.customer_id,
            customer_phone=entry.customer_phone,
            last_user_message=entry.last_user_message,
        )
        for entry in list_pending_queue_entries(db)
    ]
