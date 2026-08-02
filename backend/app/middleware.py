"""请求级中间件：correlation ID 透传 + structlog 上下文绑定。

从请求头 X-Correlation-ID 读取（缺失则生成），绑定到 structlog contextvars
使后续日志均携带 correlation_id，并回写响应头。每请求记一条 http_request 日志，
保证可观察行为：「structlog JSON 日志含 correlation ID」。
"""

from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

CORRELATION_ID_HEADER = "X-Correlation-ID"
_logger = structlog.get_logger("app.request")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get(CORRELATION_ID_HEADER) or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        _logger.info("http_request", method=request.method, path=request.url.path)
        response: Response = await call_next(request)
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response
