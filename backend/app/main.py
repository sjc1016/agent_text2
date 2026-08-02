"""FastAPI 应用入口。

F0 循环1：最小骨架，/health 端点 + structlog JSON 日志 + correlation ID 中间件。
模块边界（auth/conversation/ticket/agent/ws/scheduler）由后续切片补全。
"""

from fastapi import FastAPI

from app.agents.routes import router as agents_router
from app.auth.routes import router as auth_router
from app.conversation.routes import router as conversation_router
from app.general.routes import router as general_router
from app.inquiry.routes import router as inquiry_router
from app.logging import configure_logging
from app.middleware import CorrelationIdMiddleware
from app.ticket.routes import router as ticket_router
from app.transaction.routes import router as transaction_router
from app.ws.routes import router as ws_router

configure_logging()

app = FastAPI(title="电信客服 Agent v1")
app.add_middleware(CorrelationIdMiddleware)
app.include_router(auth_router)
app.include_router(agents_router)
app.include_router(conversation_router)
app.include_router(ticket_router)
app.include_router(transaction_router)
app.include_router(general_router)
app.include_router(inquiry_router)
app.include_router(ws_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
