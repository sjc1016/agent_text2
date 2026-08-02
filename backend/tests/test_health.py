"""F0 循环1：GET /health 返回 200 + structlog JSON 日志含 correlation ID。

验收标准（issue #2）：
  后端 FastAPI 应用启动，GET /health 返回 200，structlog JSON 日志含 correlation ID
  （PRD 依据：实现决策 › 模块划分；测试决策 › HTTP 集成 seam）

通过 HTTP 公共接口（httpx ASGITransport）验证，不测实现细节。
"""

import json


async def test_health_returns_200_ok(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_propagates_correlation_id_and_logs_json(client, log_stream):
    """同一验收标准的「structlog JSON 日志含 correlation ID」行为。

    通过 HTTP 接口可观察两点：
    1. 请求头 X-Correlation-ID 被回传到响应头（中间件透传）；
    2. structlog 输出行可解析为 JSON，且至少一条含 correlation_id。
    """
    response = await client.get("/health", headers={"X-Correlation-ID": "cid-test-123"})

    assert response.headers["X-Correlation-ID"] == "cid-test-123"

    log_lines = [line for line in log_stream.getvalue().splitlines() if line.strip()]
    assert log_lines, "expected at least one structured log line"
    parsed = [json.loads(line) for line in log_lines]
    assert any(event.get("correlation_id") == "cid-test-123" for event in parsed)
