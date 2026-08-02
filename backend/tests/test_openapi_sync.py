"""F0 循环6：OpenAPI schema 同步守卫。

验收标准（issue #2 / PRD › API 文档：OpenAPI 自动生成）：
  backend/openapi.json 与 app.openapi() 一致（CI 守卫漂移），
  且含 F0 已实现的 /health 端点。
"""

import json
from pathlib import Path

from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = REPO_ROOT / "backend" / "openapi.json"


def test_committed_openapi_in_sync() -> None:
    """committed openapi.json 必须与当前 app.openapi() 逐字一致。"""
    committed = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert committed == app.openapi()


def test_openapi_includes_health_endpoint() -> None:
    schema = app.openapi()
    assert "/health" in schema["paths"]
