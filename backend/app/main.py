"""FastAPI 应用入口。

F0 循环1：最小骨架，/health 端点 + structlog JSON 日志 + correlation ID 中间件。
模块边界（auth/conversation/ticket/agent/ws/scheduler）由后续切片补全。
"""

from fastapi import FastAPI

from app.auth.routes import router as auth_router
from app.logging import configure_logging
from app.middleware import CorrelationIdMiddleware

configure_logging()

app = FastAPI(title="电信客服 Agent v1")
app.add_middleware(CorrelationIdMiddleware)
app.include_router(auth_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
