"""B2 循环4：WebSocket 连接 JWT 查询参数鉴权。

验收标准（issue #7）：
  WebSocket 连接用 JWT 查询参数鉴权，未授权拒绝
  （PRD 依据：实现决策 › API 契约 / WebSocket 事件；
              实现决策 › 认证与会话 — REST 用 Authorization header，WS 用 JWT 查询参数）

鉴权语义与 B1 REST 一致（access type + 合法 sub + 客户存在），
差异仅取参位置：WS 从查询参数 `token` 取，握手失败用 close code 4401 拒绝
（HTTP 401 在 WS 握手层无对应，应用层 close code 4xxx 表达「未授权」）。
"""

import bcrypt
import pytest
from starlette.websockets import WebSocketDisconnect

pytestmark = pytest.mark.integration

_BCRYPT_ROUNDS = 12


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def _create_customer(db, phone: str = "13900000020", password: str = "svc12345"):
    from app.models import Customer

    customer = Customer(phone=phone, service_password_hash=_hash_password(password))
    db.add(customer)
    db.commit()
    return customer


def test_ws_without_token_rejected(ws_client):
    """无 token 查询参数 → 握手拒绝（close code 4401）。"""
    with pytest.raises(WebSocketDisconnect) as exc, ws_client.websocket_connect("/ws"):
        pass
    assert exc.value.code == 4401


def test_ws_with_empty_token_rejected(ws_client):
    """token 空串 → 拒绝。"""
    with pytest.raises(WebSocketDisconnect) as exc, ws_client.websocket_connect("/ws?token="):
        pass
    assert exc.value.code == 4401


def test_ws_with_invalid_token_rejected(ws_client):
    """非合法 JWT → 拒绝。"""
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        ws_client.websocket_connect("/ws?token=not.a.valid.jwt"),
    ):
        pass
    assert exc.value.code == 4401


def test_ws_with_refresh_token_rejected(ws_client, db):
    """refresh token 不得访问 WS（仅 access type 放行）。"""
    from app.auth.security import create_refresh_token

    customer = _create_customer(db)
    refresh = create_refresh_token(customer.id)

    with (
        pytest.raises(WebSocketDisconnect) as exc,
        ws_client.websocket_connect(f"/ws?token={refresh}"),
    ):
        pass
    assert exc.value.code == 4401


def test_ws_with_token_for_nonexistent_customer_rejected(ws_client, db):
    """token sub 指向不存在的客户 → 拒绝（防伪造/已删除客户）。"""
    from app.auth.security import create_access_token

    # 用一个 DB 中不存在的 customer_id 签 token
    token = create_access_token(999999)
    with (
        pytest.raises(WebSocketDisconnect) as exc,
        ws_client.websocket_connect(f"/ws?token={token}"),
    ):
        pass
    assert exc.value.code == 4401


def test_ws_with_valid_access_token_accepted(ws_client, db):
    """有效 access token → 握手成功，连接保持（循环4 服务端不主动发消息）。"""
    from app.auth.security import create_access_token

    customer = _create_customer(db, phone="13900000021")
    token = create_access_token(customer.id)

    with ws_client.websocket_connect(f"/ws?token={token}") as ws:
        # 进入上下文即 accept 成功；客户端主动 close 收尾，不应抛 disconnect
        # （服务端 accept 后保持等待，循环5 起补事件收发）
        ws.close()
