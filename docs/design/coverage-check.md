# DESIGN.md §5 覆盖核对 + §6 宜忌核对留档

> 来源：issue #3（#D-global 设计输入）。
> 核对对象：`docs/design/DESIGN.md` §5 通用原语 + §6 宜忌，对 `docs/prd/telecom-customer-service-agent-v1.md` 全部 11 页 UI 设计描述。
> 目的：复核并固化 PRD「DESIGN 合规自检」声明，确认 §5 原语覆盖无缺口、§6 宜忌无违反，供后续 UI 切片引用。

## 一、§5 通用原语清单（issue #3 设计输入清单所列）

| 原语 | DESIGN.md 章节 |
|---|---|
| 顶栏 | §5.5 导航（顶栏） |
| 侧栏 | §5.5 导航（侧栏） |
| 底栏 Tab | §5.5 导航（底栏 Tab） |
| 卡片 | §5.3 卡片容器 |
| 列表行 | §5.4 列表行 |
| 按钮 | §5.1 按钮与交互（主/次/描边/文字/反色） |
| 输入 | §5.2 输入与表单 |
| 徽章 | §5.7 状态徽章 |
| 搜索框 | §5.6 搜索框 |
| 空状态 | §5.9 空状态 |
| Loading | §5.10 Loading（Spinner/骨架屏/信号脉冲/全屏加载） |
| 信号脉冲 | §5.10 Loading › 信号脉冲（签名动效） |

补充原语（PRD 各页实际复用，未在 issue 清单但 §5 已定义）：§5.8 图标按钮。

## 二、逐页 §5 原语覆盖矩阵

符号：✓ = 该页 UI 设计描述复用此原语；— = 不适用。

| 页面（platform-id / page-id） | 顶栏 | 侧栏 | 底栏Tab | 卡片 | 列表行 | 按钮 | 输入 | 徽章 | 搜索框 | 空状态 | Loading | 信号脉冲 | 图标按钮 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| customer-web / app-shell | ✓ | — | ✓ | — | — | — | — | ✓ | — | — | — | — | — |
| customer-web / auth | — | — | — | ✓(Modal) | — | ✓(主/文字) | ✓ | — | — | — | ✓ | — | ✓(眼睛) |
| customer-web / chat | ✓(壳层) | — | ✓(壳层) | ✓(气泡/Modal) | — | ✓(主/次/文字/图标) | ✓ | ✓ | — | ✓(问候泡) | ✓(骨架屏) | ✓ | ✓(发送/重发) |
| customer-web / tickets | ✓(壳层) | — | ✓(壳层) | ✓(嵌套) | ✓ | — | — | ✓ | — | ✓ | ✓(骨架屏) | — | ✓(类型) |
| customer-web / profile | ✓(壳层) | — | ✓(壳层) | ✓ | ✓ | ✓(文字/反色) | — | ✓ | — | ✓ | — | — | ✓(头像) |
| agent-console / app-shell | ✓ | ✓ | — | — | — | — | — | ✓(未读计数) | ✓ | — | — | — | ✓(状态/登出) |
| agent-console / login | — | — | — | ✓(Modal) | — | ✓(主) | ✓ | — | — | — | ✓ | — | ✓(眼睛) |
| agent-console / queue | ✓(壳层) | ✓(壳层) | — | ✓(统计条) | ✓(高亮未读) | ✓(主/描边) | — | ✓ | — | ✓ | ✓(骨架屏) | — | ✓(刷新) |
| agent-console / active-chat | ✓(壳层) | ✓(壳层) | — | ✓(气泡/嵌套/Modal) | ✓(紧凑) | ✓(主/次/文字/图标) | ✓ | ✓ | — | ✓ | ✓(骨架屏) | ✓ | ✓(发送) |
| agent-console / tickets | ✓(壳层) | ✓(壳层) | — | ✓(筛选栏) | ✓(选中色条) | ✓(主/描边/文字) | ✓(Select) | ✓ | ✓(筛选) | ✓ | ✓(骨架屏) | — | — |
| agent-console / ticket-detail | ✓(壳层) | ✓(壳层) | — | ✓ | ✓(紧凑) | ✓(主/描边/文字) | ✓(Select) | ✓ | — | ✓ | ✓(骨架屏) | — | ✓(返回) |

**覆盖结论：** issue #3 所列 11 项原语 + §5.8 图标按钮，在 11 页 UI 设计描述中均有复用；**无页面需要 §5 未定义的原语，无原语缺口**。PRD 末尾摘要「待扩展 DESIGN §5 项：无」属实。

## 三、§6 宜忌逐条核对

### 应当

| 宜忌条目 | 核对结果 |
|---|---|
| 应当用色调叠层与背景色阶分隔区块 | ✓ 11 页均用 `Neutral 100` 极淡线（顶栏底/侧栏右/Modal Header 下/列表行底）+ 阴影（`shadow-xs`~`shadow-lg`）分区，无实线边框分隔区块 |
| 应当聚焦态用环不用边框 | ✓ auth / login / chat / active-chat 输入框聚焦均移除描边改 `shadow-focus`；错误态用 `semantic-error 100` 环 |
| 应当用信号脉冲表达 LLM 等待 | ✓ chat 与 active-chat 对话流「助理正在生成」用信号脉冲（3 圆点 `Primary 500` 脉动）；Handoff 等待接入亦用信号脉冲 |
| 应当每屏主按钮最多 1 个 | ✓ 各页主操作仅 1 个主按钮（chat 发送/二次确认「确认办理」/复核「确认执行」；queue「接入」；ticket-detail 按状态单主按钮；auth/login「认证」/「登录」），次操作用次/描边/文字按钮 |
| 应当列表选中态用左侧色条 + 背景色 | ✓ tickets 列表选中 `primary-tint-bg-strong` + 左侧 3px `Primary 500` 色条；侧栏菜单选中按 §5.5 明确「不用色条靠背景与文字色」（侧栏除外，合规） |

### 禁止

| 宜忌条目 | 核对结果 |
|---|---|
| 禁止用实线边框分隔区块 | ✓ 全文无 `1px Neutral 300+` 实线分隔区块；输入框默认态 `1px Neutral 300` 描边属表单元素标识（§2 无描边规则允许），聚焦/错误态移除 |
| 禁止错误态用临时 HEX | ✓ auth / login 错误态均引用 `semantic-error 100`（环）/ `semantic-error 500`（文案）Token，无裸写 `#E53935` |
| 禁止裸写叠色简写 | ✓ 11 页均引用 §4 Token 名（`primary-tint-bg` / `primary-tint-bg-strong` / `tertiary-tint-bg` / `semantic-info-tint-bg` / `semantic-warning-tint-bg` / `semantic-error-tint-bg` / `neutral-overlay`），无 `@ N%` 简写 |
| 禁止徽章写业务状态名或状态色映射 | ✓ §5.7 仅定义 6 变体组件形态 + 通用样例；业务状态（待执行/处理中/已生效等）→ 徽章变体映射写在 PRD `tickets` 页与状态策略，未污染 DESIGN.md |
| 禁止自定义字体或加载 Web 字体 | ✓ 11 页均用系统字体（PingFang SC / Microsoft YaHei），DESIGN.md §3 明确不引入 Web 字体 |

**宜忌结论：** §6 五条「应当」+ 五条「禁止」逐条核对，11 页 UI 设计描述**无违反**。PRD「DESIGN 合规自检」声明属实。

## 四、spec-driven 模式核对

- PRD 文首声明 `UI 模式：spec-driven`，文末摘要重申。
- 11 页 UI 设计描述均以文字描述布局/层级/组件/交互/变体，**全文无设计稿路径、无 PNG 引用**。
- `docs/design/references/customer-web-chat.html` 为交互/布局灵感参考（见其 README.md），非 mockup SSOT，不触发 mockup-driven 切换。
- DESIGN.md §3 字体实现约束「不适用」（纯 Web 无受限运行时），与 platforms.md 受限运行时说明一致。

## 五、最终结论

| 核对项 | 结果 |
|---|---|
| §5 原语覆盖 PRD 11 页 | ✓ 无缺口 |
| §6 宜忌在 11 页无违反 | ✓ 无违反 |
| spec-driven 无 PNG 稿要求 | ✓ 确认 |
| 受限运行时 | ✓ 不适用（纯 Web） |
| 缺口标注为后续 #D-xxx | 无需（无缺口） |

本核对记录留档供后续 UI 切片（`UI-C-*` / `UI-A-*`）引用，确认 `docs/design/DESIGN.md` §5/§6 已就绪作为各页实现的品牌视觉 SSOT。
