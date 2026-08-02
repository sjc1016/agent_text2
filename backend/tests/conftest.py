"""测试共享 fixtures。

- client: 通过 ASGITransport 挂载 FastAPI app 的 httpx AsyncClient，走真实 ASGI 栈
  （含中间件），不耦合实现细节。
- db: 临时 SQLite 会话，建表后供测试直接播种数据。
- db_client: 带 DB 的 HTTP client，override get_db 指向与 db 同一临时库。
- log_stream: 将 structlog 指向 StringIO 供捕获，测试后恢复默认 stderr。
"""

import io
from collections.abc import Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_db
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
    engine = sa_create_engine(url)
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
    engine = sa_create_engine(url)
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
