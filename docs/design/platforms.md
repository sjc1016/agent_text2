# 多端平台清单

> 用途：登记电信客服 Agent v1 全部交付端，作为 UI 切片引用 `platform-id` 的 SSOT。
> 来源：issue #3（#D-global 设计输入）；与 `docs/prd/telecom-customer-service-agent-v1.md`「页面清单」、`docs/design/DESIGN.md` §3 字体实现约束对齐。

## 平台清单

| platform-id | 端名称 | 运行环境 | 技术栈 | 组件库 | 跨端组件库差异 | 受限运行时 |
|---|---|---|---|---|---|---|
| `customer-web` | 用户端 | 浏览器 | Vue3 + Vite + Vue Router + Pinia | Element Plus | 无 | 无 |
| `agent-console` | 坐席工作台 | 浏览器 | Vue3 + Vite + Vue Router + Pinia | Element Plus | 无 | 无 |

## 跨端差异说明

两端均为纯 Web 浏览器端，技术栈完全一致（Vue3 + Element Plus），**无跨端组件库差异**：

- 同一套组件库（Element Plus），同一套品牌 Token（`docs/design/DESIGN.md` §2 色板、§3 字体、§4 叠色、§5 通用原语）。
- 差异仅在布局与功能页组合（用户端底栏 Tab 对话为主入口；坐席工作台侧栏导航队列/会话/工单），由 PRD 各页 UI 设计描述定义，不在平台清单层体现。
- 不存在移动端原生、小程序、SSR 等异构运行时，无需条件编译或平台分支。

## 受限运行时说明

**不适用。** 两端均为纯 Web（Vue3 + Element Plus），无受限运行时：

- `docs/design/DESIGN.md` §3「字体实现约束（受限运行时须填写）」已注明「不适用，跳过」——技术栈为纯 Web，不引入自定义字体，使用系统字体降级（PingFang SC / Microsoft YaHei），无 FOUT、无加载策略需求。
- 无离线包、无 WebView 桥接、无原生权限限制，浏览器标准 API（WebSocket、Fetch、localStorage）全可用。

## UI 模式

`spec-driven`（来源：`docs/design/DESIGN.md` 文首 `> UI 模式：spec-driven`）。

- UI 设计描述为编码的唯一权威来源（SSOT），**无 PNG 设计稿要求**。
- 状态变体一律写入 PRD 各页 UI 设计描述的变体段，不依赖设计稿标注。
- `docs/design/references/` 下的 HTML 参考文件仅作交互/布局灵感（非 mockup SSOT），不触发 mockup-driven 切换；品牌视觉 SSOT 仍是 `docs/design/DESIGN.md`。

## UI 切片引用约定

UI 实现 issue（`UI-C-*` / `UI-A-*`）在 PRD 绑定中通过 `platform-id` 引用本清单：

- `customer-web` → 用户端切片（`UI-C-*`），对应 PRD `customer-web` 端页面清单（`app-shell` / `auth` / `chat` / `tickets` / `profile`）。
- `agent-console` → 坐席工作台切片（`UI-A-*`），对应 PRD `agent-console` 端页面清单（`app-shell` / `login` / `queue` / `active-chat` / `tickets` / `ticket-detail`）。

每端页面清单顺序：首条为该端 `app-shell`（整体框架），其后为功能页。
