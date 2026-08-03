"""会话与消息 REST 路由。

B2 循环2（issue #7 验收1）：
  GET /conversations — 当前客户会话列表
  GET /conversations/{id}/messages — 会话消息历史（按 created_at 升序）

鉴权复用 B1 的 CurrentCustomer（Authorization header Bearer）。
PRD 依据：实现决策 › API 契约 / RESTful 端点；测试决策 › HTTP 集成 seam；US-1。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentCustomer
from app.conversation.schemas import ConversationOut, MessageOut
from app.conversation.service import (
    create_conversation,
    get_customer_conversation_or_none,
    list_conversations_for_customer,
    list_messages_for_conversation,
)
from app.db import get_db
from app.models import Conversation, Message

router = APIRouter(prefix="/conversations", tags=["conversation"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[ConversationOut])
def list_conversations(current: CurrentCustomer, db: DbSession) -> list[Conversation]:
    """当前客户的会话列表（未认证 401 由 CurrentCustomer 守卫）。"""
    return list_conversations_for_customer(db, current)


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
def create_conversation_route(current: CurrentCustomer, db: DbSession) -> Conversation:
    """认证客户创建新会话（PRD › API 契约 /conversations 会话 CRUD；#24 对话页入口）。

    新会话以 authenticated 起步（客户已认证）；消息流经 WS /ws 发送到该会话。
    """
    return create_conversation(db, current)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(conversation_id: int, current: CurrentCustomer, db: DbSession) -> list[Message]:
    """会话消息历史；会话不存在或不属于当前客户 → 404（不泄露存在性）。"""
    conv = get_customer_conversation_or_none(db, current, conversation_id)
    if conv is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return list_messages_for_conversation(db, conversation_id)
