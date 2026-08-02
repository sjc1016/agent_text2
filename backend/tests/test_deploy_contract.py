"""F0 循环7：nginx 配置 + uvicorn 启动脚本就绪（手动启动，不自启）。

验收标准（issue #2）：
  nginx 配置 + uvicorn 启动脚本就绪（手动启动，不自启）
  （PRD 依据：实现决策 › 部署；ADR 0006 › 部署方式 / 运行时）

契约性断言（非实现细节）：
  - deploy/nginx.conf 存在，且承载三项对外契约：
      * 两端静态托管（customer-web / agent-console 各一 server 块，不同端口）
      * /api/ 与 /ws 反代到后端（127.0.0.1:8000）
      * /ws 走 WebSocket 升级（Upgrade / Connection）
  - deploy/start_backend.ps1 存在，承载后端启动契约：
      * uvicorn 拉起 app.main:app
      * 绑定 127.0.0.1:8000（仅本机，由 nginx 反代对外）

端口分配（本切片约定，ADR 0006 未指定）：
  80   → 用户端 customer-web
  8081 → 坐席工作台 agent-console
  8000 → uvicorn（仅本机）

「可启动 / 可渲染」由人工冒烟（README 指引）验证，不在本测试内拉起真实进程。
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NGINX_CONF = REPO_ROOT / "deploy" / "nginx.conf"
START_SCRIPT = REPO_ROOT / "deploy" / "start_backend.ps1"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing deploy artifact: {path.relative_to(REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


def test_deploy_directory_exists():
    assert (REPO_ROOT / "deploy").is_dir(), "deploy/ directory missing at repo root"


def test_nginx_config_exists():
    assert NGINX_CONF.is_file(), "deploy/nginx.conf missing"


def test_nginx_serves_both_frontends_on_distinct_ports():
    conf = _read(NGINX_CONF)
    # 两个前端各一 server，不同端口（避免端口冲突；F0 骨架前端无路由，无需 base path）
    assert "listen 80" in conf, "nginx missing customer-web listen 80"
    assert "listen 8081" in conf, "nginx missing agent-console listen 8081"
    # 静态产物根（vite 默认 outDir=dist）
    assert "customer/dist" in conf, "nginx missing customer-web static root"
    assert "agent/dist" in conf, "nginx missing agent-console static root"


def test_nginx_proxies_api_and_ws_to_backend():
    conf = _read(NGINX_CONF)
    # /api/ 与 /ws 反代到后端（uvicorn 127.0.0.1:8000）
    assert "127.0.0.1:8000" in conf, "nginx missing backend upstream 127.0.0.1:8000"
    assert "/api/" in conf, "nginx missing /api/ proxy location"
    assert "/ws" in conf, "nginx missing /ws proxy location"
    assert "proxy_pass" in conf, "nginx missing proxy_pass directive"


def test_nginx_ws_upgrade_headers():
    conf = _read(NGINX_CONF)
    # WebSocket 升级头（缺则 /ws 握手失败）
    assert "Upgrade" in conf, "nginx missing WebSocket Upgrade header"
    assert "upgrade" in conf.lower(), "nginx missing WebSocket Connection upgrade"


def test_start_backend_script_exists():
    assert START_SCRIPT.is_file(), "deploy/start_backend.ps1 missing"


def test_start_backend_script_launches_uvicorn_on_loopback():
    script = _read(START_SCRIPT)
    # uvicorn 拉起 app.main:app，绑定本机 8000（ADR 0006: 单进程，仅本机）
    assert "uvicorn" in script, "start script missing uvicorn invocation"
    assert "app.main:app" in script, "start script missing app.main:app entrypoint"
    assert "127.0.0.1" in script, "start script missing loopback bind"
    assert "8000" in script, "start script missing port 8000"
