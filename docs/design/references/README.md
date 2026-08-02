# 设计参考（references/）

本目录存放**外部设计参考**——用于交互模式与布局灵感，**不是**项目的 mockup SSOT。

## 身份声明（重要）

- 项目 UI 模式为 **`spec-driven`**（见 `docs/design/DESIGN.md` 文首与 PRD 摘要）。
- **品牌视觉 SSOT 是 `docs/design/DESIGN.md`**：色板（电信蓝/信号青/暖橙/石墨灰）、浅底深字基调、无描边规则、无渐变/无毛玻璃。
- 本目录任何参考文件的**配色、渐变、毛玻璃、字体等视觉处理一律忽略**，实现时**只认 DESIGN.md**。
- 本目录文件**不触发** `mockup-driven` 切换，也**不作为** `#D-xxx` 默认态 PNG。UI 实现 issue 的 SSOT 仍是 PRD 页面清单「UI 设计描述」+ DESIGN.md §5。
- 实现者引用本目录内容时，须将其交互/布局模式**翻译**成 DESIGN.md 的 Token 与原语，不得直接照搬视觉。

## 现有参考

| 文件 | 对应 page-id | 身份 | 说明 |
|------|--------------|------|------|
| `customer-web-chat.html` | customer-web / `chat` | 灵感参考（非 SSOT） | 第三方高保真暗色原型；仅取交互/布局模式，视觉忽略 |

---

## `customer-web-chat.html` — 可提取模式（供 #24 UI-C-3 chat 参考）

> 以下为该原型中**值得借鉴的交互/布局模式**，已与 PRD chat 页设计描述（`docs/prd/telecom-customer-service-agent-v1.md` § chat）对照。标注 ✅=PRD 已有（确认对齐）、➕=PRD 未显式定义的可选增强、⛔=与 PRD/DESIGN 冲突或超出 v1 范围（不采纳）。

### ➕ 建议气泡 chips（quick-reply suggestions）
- 原型在消息区下方、输入区上方放置可点击的快捷问题胶囊（「我这个月还剩多少流量？」「帮我查一下账户余额」…），点击即填入输入框并发送。
- **价值**：降低用户输入成本，契合「三秒内找到下一步」北极星；新会话空状态时可作引导。
- **#24 落地建议**：作为可选增强项提出。若采纳，须用 DESIGN.md 原语实现——胶囊用 `surface-card` 白底 + `Neutral 300` 细描边 + 圆角 999px（或徽章规格），悬停 `primary-tint-bg`，文字 `Neutral 700`；不得照搬原型的暗色 + 边框悬停变薄荷绿。
- **范围决策**：是否纳入由 #24 维护者定；若纳入需在 PR States 矩阵补 `suggestions` 态并标注 PRD 依据来源为「参考增强」。

### ✅ 打字指示器 ↔ 信号脉冲（已对齐）
- 原型用 3 圆点脉动动画表示 bot 生成中。
- PRD chat 页已定义「信号脉冲」（3 圆点 `Primary 500` 脉动）作为 LLM 等待签名动效。**两者一致**，确认 PRD 设计正确，按 DESIGN.md §5 Loading 实现即可，**不采纳**原型的暗色 + 灰点配色。

### ➕ composer 自适应高度
- 原型 textarea 随输入内容自动增高（上限 120px）。
- PRD chat 页输入区仅规定「回车发送 / Shift+回车换行」，未提自适应高度。
- **#24 落地建议**：低成本增强，可纳入。用 `Element Plus` `el-input` textarea `autosize` 实现，符合「克制」气质。

### ⛔ ReAct 推理轨迹面板（不采纳 / 超范围）
- 原型右侧有 Thought/Action/Observation/Answer 推理轨迹面板。
- PRD chat 页**无此结构**；客户面对终端用户，暴露推理链路超出 v1 范围（属开发/调试视图）。
- **不纳入 #24**。若后续需坐席端调试视图，另开 issue 评估，不在此参考驱动。

### ⛔ 视觉冲突项（一律忽略）
以下为原型与 DESIGN.md 的直接冲突，实现时**不得**采用：
- 暗色基调（`#0d1117` / `#141b24`）→ 用 DESIGN.md 浅底（`surface-base` `Neutral 50` / `surface-card` 白）
- 薄荷绿 `#2dd4bf` + 天蓝 `#38bdf8` 主色 → 用电信蓝 `Primary 500 #1A6FFF` + 信号青 `Secondary 500 #00B8D4`
- `linear-gradient`（logo/按钮/气泡/头像）→ DESIGN.md §2 禁止渐变
- `backdrop-filter:blur`（顶栏毛玻璃）→ DESIGN.md §2 不适用
- 用户气泡渐变填充 → PRD 规定用户气泡为 `Primary 500` 纯色底白字
- 圆角 14px/16px → 用 DESIGN.md 统一圆角（卡片 8px / 按钮 6px / 弹层 12px）

### ⛔ 超范围视图（不采纳）
原型含「Agent 架构 / 工具中心 / 知识库 RAG」三个视图与侧栏导航——均不在 PRD customer-web 5 页范围内，属原型作者的展示性内容，**不纳入**项目。

---

## 维护规则

- 新增参考文件须在本 README 登记一行（文件 / page-id / 身份 / 说明）。
- 参考文件命名：`{platform-id}-{page-id}.<ext>`（与 mockup-driven references 命名一致，便于将来切换）。
- 任何参考文件入库时，须同步在本文件补充「可提取模式」与「视觉冲突项」对照，避免实现者误照搬。
