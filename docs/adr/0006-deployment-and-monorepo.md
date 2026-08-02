# 部署形态与 Monorepo

采用模块化单体架构,单一 FastAPI 应用内部分模块(auth、conversation、ticket、agent、ws、scheduler)。部署形态为本地 Windows 裸机生产模式:uvicorn 单进程直接跑,nginx 托管前端静态产物并反代 `/api` 与 `/ws`,SQLite 文件落本地磁盘(开启 WAL 模式),APScheduler 进程内调度,手动启动不自启。Monorepo 结构:`frontend/customer/`(用户端)、`frontend/agent/`(坐席工作台)、`frontend/shared/`(共享类型)、`backend/`(FastAPI + LangChain);前端用 pnpm workspace,后端用 uv。

## Status

accepted

## Considered Options

**部署架构:**

- **模块化单体** — 选定。v1 流量不大,微服务过度设计;SQLite 单库不支持跨服务事务;模块边界清晰,v2 可按模块拆服务。
- **微服务** — 否决。需独立部署 + 服务发现 + 分布式事务,复杂度爆炸。
- **无模块化单体** — 否决。代码混乱,演进困难。

**部署方式:**

- **本地 Windows 裸机** — 选定。v1 聚焦功能验证,手动启动,不引入 Docker。
- **Docker Compose** — 否决。用户明确选本地裸机。
- **Kubernetes** — 否决。过度。

**运行时:**

- **uvicorn 单进程** — 选定。契合手动启动与本地裸机;未来上生产服务器需多 worker 时,可平滑切换 gunicorn + uvicorn worker。
- **gunicorn + uvicorn worker** — 否决(仅本地运行无需多进程)。

**Monorepo 工具:**

- **pnpm workspace + uv** — 选定。前端用 pnpm 主流,后端用 uv(用户熟悉),不引入 Nx/Turborepo 复杂度。
- **Nx / Turborepo** — 否决。v1 两个前端 + 一个后端,过度。

## Consequences

- v1 仅本地 Windows,nginx 用 Windows 版,后续上 Linux 需补 Dockerfile 与跨平台脚本。
- 手动启动:进程崩溃不自动重启,需人工拉起;v2 上生产应改 NSSM 或 Docker。
- SQLite WAL 模式必须开启,避免读写锁竞争。
- 模块化边界必须在代码层强制(目录隔离 + import 规范),否则单体易退化为大泥球。
