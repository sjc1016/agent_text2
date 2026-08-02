"""测试共享 fixtures。

- client: 通过 ASGITransport 挂载 FastAPI app 的 httpx AsyncClient，走真实 ASGI 栈
  （含中间件），不耦合实现细节。
- db: 临时 SQLite 会话，建表后供测试直接播种数据。
- db_client: 带 DB 的 HTTP client，override get_db 指向与 db 同一临时库。
- log_stream: 将 structlog 指向 StringIO 供捕获，测试后恢复默认 stderr。
"""

import io
from collections.abc import Callable, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.orm import Session, sessionmaker

from app.db import create_engine, get_db
from app.logging import configure_logging
from app.main import app
from app.models import Base


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


@pytest.fixture
def db(tmp_path):
    """临时 SQLite 会话：建表后供测试直接播种数据。与 db_client 共享同一 tmp_path DB。"""
    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)
    session = test_session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
async def db_client(tmp_path, db):
    """带 DB 的 HTTP client：override get_db 指向与 db fixture 同一临时库。"""
    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(url)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db() -> Generator[Session, None, None]:
        session = test_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.fixture
def ws_client(tmp_path):
    """同步 WS 测试 client（starlette TestClient）+ DB override 指向临时库。

    httpx AsyncClient 不支持 WebSocket；WS 测试用 starlette 同步 TestClient，
    走同一 ASGI 栈（含中间件与 dependency_overrides）。与 db fixture 共享 tmp_path
    库文件，可在测试中先用 db 播种客户再用 ws_client 连接鉴权。

    循环4 起的 WS 系列测试（鉴权 / 事件推送 / 状态机推送）复用本 fixture。
    """
    from starlette.testclient import TestClient

    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db() -> Generator[Session, None, None]:
        session = test_session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.fixture(autouse=True)
def _reset_ws_hub():
    """测试后清空 hub 连接注册表。

    ConnectionHub 为模块级单例（单进程部署设计）；TestClient 未进 `with` 上下文时
    连接注销可能迟到，残留连接会让后续测试的推送卡在已关闭连接上（挂起）。
    每个测试后重置，保证测试间隔离（对全部测试生效，非 WS 测试无副作用）。
    """
    yield
    from app.ws.hub import hub

    hub.reset()


def ws_recv_json(session, timeout: float = 5.0) -> dict:
    """可靠接收一条 WS JSON 消息（envelope 的 data 已解析），带超时。

    背景：starlette TestClient 的 `session.receive_json()` 经 `portal.call` 阻塞
    读取，底层是 `asyncio.Event` 的跨线程 set。在 Windows + Python 3.13 +
    ProactorEventLoop 下，**两个 WS 连接并发**时（如坐席线程向客户连接推送），
    跨线程 `loop.call_soon` 不会唤醒阻塞在 IOCP select 的客户 loop，
    导致 receive 偶发永久挂起。生产环境（uvicorn 单进程单事件循环）无此问题。

    本 helper 绕开 portal 唤醒：直接轮询 session 的发送端缓冲（receive_nowait），
    消息只要被 push 进入缓冲即取到；超时抛 TimeoutError（测试失败而非挂起）。
    仅双连接测试使用；单连接 + REST 触发推送场景（push 阻塞完成于 receive 前）
    无需改动。
    """
    import json
    import time

    from anyio import WouldBlock
    from starlette.websockets import WebSocketDisconnect

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            raw = session._send_rx.receive_nowait()
        except WouldBlock:
            time.sleep(0.005)
            continue
        if raw.get("type") == "websocket.close":
            raise WebSocketDisconnect(code=raw.get("code", 1000))
        if raw.get("type") == "websocket.send":
            if "text" in raw:
                return json.loads(raw["text"])
            if "bytes" in raw:
                return json.loads(raw["bytes"])
    raise TimeoutError(f"ws receive timed out after {timeout}s")


@pytest.fixture
def recv_ws() -> Callable[..., dict]:
    """WS 接收辅助（返回 ws_recv_json）：双连接 WS 测试用它替代 receive_json。"""
    return ws_recv_json
