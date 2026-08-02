"""F0 循环6：HTTP 集成 seam 占位（integration 标记）。

PRD 测试决策 › HTTP 集成 seam：最高层级接缝，通过 pytest + httpx AsyncClient
测试 REST 端点请求/响应形状、状态码、鉴权边界。F0 骨架阶段以 FastAPI 自动暴露的
/openapi.json 端点经完整 ASGI 栈可访问作为集成 seam tracer-bullet；后续 B-slice
的 HTTP 集成测试均标 integration，由 CI integration-test 阶段独立运行
（与 unit 阶段 `pytest -m "not integration"` 分离）。
"""

import pytest

# 整个模块标记为 integration，归入 CI integration-test 阶段
pytestmark = pytest.mark.integration


async def test_openapi_endpoint_accessible_via_asgi(client) -> None:
    """/openapi.json 经完整 ASGI 栈可访问，且含 /health（集成 seam 雏形）。"""
    response = await client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["openapi"].startswith("3.")
    assert "/health" in schema["paths"]
