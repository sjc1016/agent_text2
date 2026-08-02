# 技术栈基线与语言策略

电信客服 Agent 项目采用多语言栈:后端 Python(FastAPI + LangChain),前端 TypeScript(Vue3),数据库 SQLite。LangChain 在 Python 生态最成熟,FastAPI 异步契合 LLM 长耗时 IO;Vue3 + TS 是前端主流;SQLite 适合 v1 轻量起步。

## Status

accepted

## Considered Options

- **多语言(Python + TS + SQLite)** — 选定。LangChain Python 生态最成熟,Vue3 + TS 前端主流,SQLite 轻量。
- **全栈 TypeScript(Node + Vue)** — 否决。LangChain.js 生态不如 Python 完整,RAG/工具链支持弱;且后端 IO 密集型场景 Python 异步生态更成熟。

## Consequences

- 前后端需独立包管理:后端 uv,前端 pnpm workspace(见 ADR-0006 Monorepo)。
- 类型契约需 OpenAPI 自动生成 + openapi-typescript 同步(见 ADR-0003 API 风格)。
- 部署需同时构建前端静态产物与后端 Python 运行时(见 ADR-0006 部署形态)。
