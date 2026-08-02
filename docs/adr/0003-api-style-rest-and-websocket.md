# API 风格:RESTful + WebSocket 混合

采用 REST + WebSocket 混合 API:CRUD 资源端点(`/conversations`、`/tickets`、`/messages`)用 RESTful + OpenAPI 自动生成文档;实时事件(LLM 流式 token、坐席消息、`System Message`、`Notification`、`Handoff`、坐席状态)用 WebSocket 双向长连接推送。WS 事件契约通过共享 TS 定义 + 后端 Pydantic 镜像维护。

## Status

accepted

## Considered Options

- **REST + SSE 流式** — 否决。Handoff 是双向事件(坐席→用户 / 用户→坐席),SSE 单向推送不够。
- **纯 WebSocket** — 否决。WS 承载 CRUD 状态管理复杂,认证/重连/幂等成本高,且无法用 OpenAPI 文档化。
- **REST + WebSocket 混合** — 选定。REST 便于契约文档与测试,WS 契合实时双向事件;LLM 流式输出走 WS 消息流。

## Consequences

- 前端需两套客户端:REST 用 axios/fetch,WS 用原生 + 自封装重连/心跳。
- WS 事件契约靠人工镜像维护(`frontend/shared/events.ts` SSOT ↔ `backend/app/ws/events.py`),CI 加脚本校验事件名一致。
- OpenAPI 仅覆盖 REST 端点,WS 文档单独维护。
