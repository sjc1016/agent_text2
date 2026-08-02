"""测试共享 fixtures。

- client: 通过 ASGITransport 挂载 FastAPI app 的 httpx AsyncClient，走真实 ASGI 栈
  （含中间件），不耦合实现细节。
- log_stream: 将 structlog 指向 StringIO 供捕获，测试后恢复默认 stderr，避免
  全局日志状态在测试间泄漏。
"""

import io

import pytest
from httpx import ASGITransport, AsyncClient

from app.logging import configure_logging
from app.main import app


@pytest.fixture
def log_stream():
    stream = io.StringIO()
    configure_logging(stream=stream)
    yield stream
    configure_logging()  # 恢复默认 stderr


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
