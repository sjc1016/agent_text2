# 部署（本地 Windows 裸机）

对应：ADR 0006（部署形态与 Monorepo）/ F0 循环7（issue #2 验收 7）。

部署形态：模块化单体 + 本地裸机 Windows + uvicorn 单进程 + nginx 静态托管与反向代理 + **手动启动不自启**。

## 端口约定

| 端口 | 服务 | 说明 |
|------|------|------|
| 80   | nginx → customer-web | 用户端静态产物 |
| 8081 | nginx → agent-console | 坐席工作台静态产物 |
| 8000 | uvicorn（仅本机） | 后端 API + WebSocket，由 nginx 反代对外，不直接暴露 |

## 启动顺序

### 1. 构建前端

```powershell
pnpm --filter customer-web build
pnpm --filter agent-console build
```

产物分别落在 `frontend/customer/dist`、`frontend/agent/dist`（vite 默认 `outDir`）。

### 2. 应用数据库迁移（首次或迁移变更后）

```powershell
cd backend
uv run alembic upgrade head
```

SQLite 开启 WAL 模式（ADR 0006 Consequences），迁移可逆（`alembic downgrade -1`）。

### 3. 启动后端

```powershell
powershell -ExecutionPolicy Bypass -File deploy/start_backend.ps1
```

脚本拉起 `uvicorn app.main:app --host 127.0.0.1 --port 8000`。**进程崩溃不自动重启**，需人工重新执行。

### 4. 启动 nginx

1. 下载 [nginx for Windows](http://nginx.org/en/download.html)，解压到任意目录。
2. 用 `deploy/nginx.conf` 替换 `<nginx>/conf/nginx.conf`，或在其 `http` 块内 `include` 本文件。
3. 按需调整 `root` 路径为前端 `dist` 的实际绝对路径（配置内注释处有示例）。
4. 启动：`<nginx>\nginx.exe`；重载配置：`nginx -s reload`；停止：`nginx -s quit`。

## 冒烟验证

- 后端健康检查：`curl http://127.0.0.1:8000/health` → `{"status":"ok"}`
- 经 nginx 访问用户端：浏览器打开 `http://localhost`
- 经 nginx 访问坐席台：浏览器打开 `http://localhost:8081`

## 已知限制（ADR 0006 Consequences）

- v1 仅本地 Windows，nginx 用 Windows 版；后续上 Linux 需补 Dockerfile 与跨平台脚本。
- 手动启动，无守护；v2 上生产应改 NSSM 或 Docker。
- 仅 uvicorn 单进程；未来需多 worker 时可平滑切换 gunicorn + uvicorn worker（Linux）。
