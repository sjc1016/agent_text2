# 电信客服 Agent v1

一个面向电信用户的智能客服系统：LLM 主导多轮对话与意图识别，通过 tools 调用业务能力（查询话费、办理套餐、报修等）。查询类（只读）直接返回；办理类（写入/不可逆）走二次确认与工单队列；特定条件下自动转人工坐席。

## 核心能力

- **四类业务能力**：查询类（认证后只读查询）、办理类（二次确认 + 工单入队 + 执行前服务密码复核）、通用咨询类（访客免认证）、工单类（故障报修等跟踪事项）
- **LLM 助理**：多轮对话、意图识别、tools 调用；支持流式输出与主/备 provider 自动切换；`llm_api_key` 为空时回退 FakeListLLM 占位，便于本地无 Key 开发
- **转人工（Handoff）**：超出能力范围、办理失败、用户明确请求、负面情绪、同一意图循环、合规风险 6 类条件自动触发；坐席工作台接单，助理退至后台协同，坐席可显式转回
- **工单（Ticket）统一模型**：办理类与工单类走不同状态机，状态变化通过站内通知推送用户
- **会话状态机**：未认证 → 已认证 → 办理中 → 已转人工 → 已结束，服务密码是访客升格客户的凭证
- **RAG**：sqlite-vec 向量检索政策文档/业务规则，回答依赖非结构化知识时避免编造
- **合规留痕**：服务密码认证、查询/办理关键操作、Handoff、坐席操作均入审计日志

v1 业务范围与明确排除项见 [CONTEXT.md](CONTEXT.md)。

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | Vue 3 + Vite + Element Plus + Pinia + Vue Router + TypeScript |
| 后端 | Python 3.9+ / FastAPI + LangChain（模块化单体） |
| 数据库 | SQLite（WAL 模式）+ sqlite-vec 向量扩展，SQLAlchemy 2.0 + Alembic 迁移 |
| 实时通信 | WebSocket（消息流式、Handoff、通知、坐席接管） |
| 任务队列 | APScheduler（SQLite 持久化，工单执行、坐席状态监控、会话超时） |
| 认证 | JWT 无状态会话（access 2h / refresh 7d / 办理执行复核 10min），bcrypt 存储密码 |
| 日志/可观测 | structlog JSON 日志 + correlation ID；Prometheus 业务指标 |
| 工具链 | pnpm workspace + uv；pre-commit；CI 8 阶段门禁 |

## 仓库结构

```
├── backend/                  # FastAPI 后端（uv 管理）
│   ├── app/
│   │   ├── auth/             # 认证、审计
│   │   ├── conversation/     # 会话状态机、REST 接口
│   │   ├── transaction/      # 办理类业务（二次确认、复核、入队）
│   │   ├── inquiry/          # 查询类业务
│   │   ├── general/          # 通用咨询 + RAG 向量检索
│   │   ├── ticket/           # 工单模型与状态机
│   │   ├── agents/           # 坐席侧 API（登录、队列、会话、工单）
│   │   ├── handoff/          # 转人工触发与服务
│   │   ├── ws/               # WebSocket 事件协议与路由
│   │   ├── scheduler/        # APScheduler 任务
│   │   └── models/           # SQLAlchemy 模型
│   ├── alembic/              # 数据库迁移脚本（0001-0010）
│   └── tests/                # pytest 测试
├── frontend/
│   ├── customer/             # 用户端 customer-web（Vite dev :5173）
│   ├── agent/                # 坐席工作台 agent-console（Vite dev :5174）
│   └── shared/               # 共享 TS 包（WebSocket 事件契约等）
├── deploy/                   # 部署配置（nginx.conf、启动脚本）
├── docs/
│   ├── adr/                  # 架构决策记录
│   ├── design/               # UI 设计规范（DESIGN.md）
│   └── prd/                  # 产品需求文档
├── scripts/                  # 工程脚本（openapi 同步、WS 事件检查等）
└── CONTEXT.md                # 领域语言与业务规则（SSOT）
```

## 快速开始（开发环境）

### 前置要求

- Node.js 20+ 与 pnpm 11（前端）
- Python 3.9+ 与 [uv](https://docs.astral.sh/uv/)（后端）
- nginx（仅部署需要，开发由 Vite 代理到后端）

### 1. 启动后端

```powershell
# 安装依赖（首次）
cd backend
uv sync

# 配置环境变量（敏感 key 不入仓库）
# 复制/创建 backend/.env，参考 backend/app/config.py 的字段（前缀 APP_）
# 至少设置：APP_LLM_API_KEY / APP_LLM_FAILOVER_API_KEY；为空时后端使用占位 LLM

# 应用数据库迁移（首次或迁移变更后）
uv run alembic upgrade head

# 启动服务（:8000，含 /api REST + /ws WebSocket + /health 健康检查）
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

> 注意：`.env` 与 SQLite 数据库文件（`*.db`）均被 [.gitignore](.gitignore) 忽略，不入仓库。

### 2. 启动前端

```powershell
# 仓库根目录安装依赖
pnpm install

# 用户端（:5173）
pnpm --filter customer-web dev

# 坐席工作台（:5174）
pnpm --filter agent-console dev
```

Vite 已配置 `/api` 与 `/ws` 代理到 `http://127.0.0.1:8000`，开发时无需 nginx。

### 3. 访问

- 用户端：http://localhost:5173
- 坐席工作台：http://localhost:5174
- 后端 API 文档（Swagger UI）：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/health

## 测试与质量

```powershell
# 后端测试（pytest，LLM 使用 mock，无 Key 也可运行）
cd backend
uv run pytest

# 前端测试与类型检查
pnpm -r test
pnpm -r type-check

# 代码风格
pnpm lint && pnpm format:check     # 前端 ESLint / Prettier
cd backend && uv run ruff check .  # 后端
```

后端测试分三层（单元/服务/集成 seam，含 HTTP 与 WS 事件），详见 [docs/adr/0005-test-strategy-and-llm-mock.md](docs/adr/0005-test-strategy-and-llm-mock.md)。

## 部署（本地 Windows 裸机）

部署形态：模块化单体 + uvicorn 单进程 + nginx 静态托管与反向代理 + 手动启动。完整步骤见 [deploy/README.md](deploy/README.md)。

| 端口 | 服务 | 说明 |
|------|------|------|
| 80   | nginx → customer-web | 用户端静态产物 |
| 8081 | nginx → agent-console | 坐席工作台静态产物 |
| 8000 | uvicorn（仅本机） | 后端 API + WebSocket，由 nginx 反代对外 |

```powershell
# 1. 构建前端
pnpm --filter customer-web build
pnpm --filter agent-console build

# 2. 应用迁移（首次或迁移变更后）
cd backend
uv run alembic upgrade head

# 3. 启动后端（不自启、不守护）
powershell -ExecutionPolicy Bypass -File deploy/start_backend.ps1

# 4. 启动 nginx（用 deploy/nginx.conf 配置，root 指向 dist）
```

## 文档导航

| 文档 | 内容 |
|------|------|
| [CONTEXT.md](CONTEXT.md) | 领域语言、业务规则、会话/工单状态机（领域 SSOT） |
| [docs/prd](docs/prd/telecom-customer-service-agent-v1.md) | 产品需求（问题陈述、用户故事、验收） |
| [docs/adr](docs/adr/) | 架构决策（技术栈、迁移纪律、API 风格、认证、测试、部署） |
| [docs/design/DESIGN.md](docs/design/DESIGN.md) | UI 设计规范（品牌色板、组件、签名动效） |
| [deploy/README.md](deploy/README.md) | 部署手册 |
| [AGENTS.md](AGENTS.md) | Agent 协作约定（Issue 跟踪、triage、领域文档布局） |
