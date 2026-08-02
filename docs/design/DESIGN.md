# 设计系统文档：电信客服 Agent

> UI 模式：`spec-driven`（规范驱动 UI，当前无稿；后续 PNG 稿齐备后可切 `mockup-driven`）

## 1. 概览与创意北极星

### 创意北极星：「Signal」

电信客服 Agent 的设计哲学是「清晰胜过炫技」（Clarity over Cleverness）。用户带着问题而来——查话费、办套餐、报故障——视觉目标是让用户快速找到入口、看清信息、确认办理，而非被视觉惊艳。客服场景的视觉判断标准不是「好不好看」，而是「用户能不能在三秒内找到下一步」。

产品气质为专业、稳定、克制、温度：专业（电信合规感，避免轻浮装饰）、稳定（数据可信，不闪烁不花哨）、克制（信息密度高但不堆砌）、温度（用户可能焦虑，避免冷冰冰）。Tertiary 暖橙的存在正是为注入温度——办理类业务强调、二次确认 Modal 的视觉提示都依赖它。

为打破模板感，采用三个手法：（1）**信号脉冲**作为贯穿签名动效——按钮微动效模拟信号波动、LLM 等待首字用三点脉动而非旋转、转场用淡入而非滑动；（2）**不对称留白**——坐席工作台左密右疏（信息密集左 / 操作稀疏右），用户端上轻下重（对话流上 / 输入区下）；（3）**层级叠色**而非硬边框分隔——卡片浮于浅灰底用阴影，选中态用背景色阶差异。这些手法让产品既不像通用 Element Plus 默认皮肤，也不像营销页那样喧宾夺主。

---

## 2. 色彩与表面架构

色板以电信蓝为品牌主色（行业隐喻 + 专业可信），辅以信号青（强调与状态指示）、暖橙（温度感来源）、石墨灰（文字与中性背景）。整体明暗基调为浅底深字——base 浅灰、card 白、文字深灰，强调高对比可读性，契合客服场景用户跨年龄层、可能焦虑需快速获取信息的诉求。

### 色板（品牌板须可视化）

| 角色 | 主色 HEX | 色阶（浅→深，附 HEX） |
|------|---------|-------------------------------|
| 主色（电信蓝） | `#1A6FFF` | 50 `#E8F2FF` / 100 `#C9DEFF` / 200 `#9CBEFF` / 300 `#6F9EFF` / 400 `#4280FF` / 500 `#1A6FFF` / 600 `#0D5BE6` / 700 `#0A47B8` / 800 `#08338A` / 900 `#062460` |
| 辅色（信号青） | `#00B8D4` | 50 `#E0F7FB` / 100 `#B2ECF5` / 200 `#80DFEF` / 300 `#4DD3E9` / 400 `#1AC7E3` / 500 `#00B8D4` / 600 `#0099B0` / 700 `#007A8C` |
| 第三色（暖橙） | `#FF8A3D` | 50 `#FFF1E5` / 100 `#FFD9BF` / 200 `#FFC299` / 300 `#FFAB73` / 400 `#FF9D5A` / 500 `#FF8A3D` / 600 `#E67026` / 700 `#B8571D` |
| 中性色（石墨灰） | `#6B7280`（正文）/ `#1F2937`（标题） | 50 `#F9FAFB` / 100 `#F3F4F6` / 200 `#E5E7EB` / 300 `#D1D5DB` / 400 `#9CA3AF` / 500 `#6B7280` / 600 `#4B5563` / 700 `#374151` / 800 `#1F2937` / 900 `#111827` |

### 语义色（品牌板须可视化）

error / success / warning / info 各定义 Token + HEX。warning 与 Tertiary 暖橙同色系但更黄（醒目），info 与 Primary 电信蓝同色系但更浅（不抢品牌色）。

| 角色 | Token | HEX | 来源 |
|------|-------|-----|------|
| 错误 | `semantic-error` | `#E53935` | 独立色（与 Tertiary 暖橙同暖系但偏红，需区分） |
| 成功 | `semantic-success` | `#2E7D32` | 独立色（与 Secondary 信号青同冷系但偏绿，需区分） |
| 警告 | `semantic-warning` | `#F9A825` | 从 Tertiary 暖橙衍生（同色系，更黄更醒目） |
| 信息 | `semantic-info` | `#0288D1` | 从 Primary 电信蓝衍生（同色系，更浅） |

语义色色阶：

- `semantic-error`：50 `#FFEBEE` / 100 `#FFCDD2` / 500 `#E53935` / 700 `#B71C1C`
- `semantic-success`：50 `#E8F5E9` / 100 `#C8E6C9` / 500 `#2E7D32` / 700 `#1B5E20`
- `semantic-warning`：50 `#FFF8E1` / 100 `#FFECB3` / 500 `#F9A825` / 700 `#F57F17`
- `semantic-info`：50 `#E1F5FE` / 100 `#B3E5FC` / 500 `#0288D1` / 700 `#01579B`

### 无描边规则

**明确指令：** 禁止用 `1px solid Neutral 300+` 实线边框分隔区块（卡片、列表行、Modal、侧栏分隔）。区块分隔改用（1）背景色阶差异（card 白浮于 base 浅灰）、（2）阴影（`shadow-xs` 至 `shadow-lg`）、（3）极淡分隔线（`1px Neutral 100` `#F3F4F6`，仅用于结构性分区如顶栏底、侧栏右、Modal Header 下）。输入框默认态保留 `1px Neutral 300` 细描边作为表单元素标识，但聚焦/错误态移除描边改用外发光环（见 §4 与 §5.2）。

圆角统一：卡片 `8px`、按钮 `6px`、输入框 `6px`、弹层 `12px`、徽章 `4px`。间距基准为 4 的倍数（4 / 8 / 12 / 16 / 24 / 32 / 48）。

### 表面层级与嵌套

| 层级 | Token | HEX | 用途 |
|------|-------|-----|------|
| base | `surface-base` | `Neutral 50` `#F9FAFB` | 页面底层背景 |
| card | `surface-card` | `白` `#FFFFFF` | 卡片、列表、表单容器 |
| modal | `surface-modal` | `白` `#FFFFFF` + `neutral-overlay` 遮罩 | Modal 弹层 |
| overlay | `surface-overlay` | `白` `#FFFFFF` + `shadow-md` | 下拉、popover、tooltip |

嵌套规则：卡片内嵌卡片时，内层去掉阴影，改用 `Neutral 50` `#F9FAFB` 底色 + 6px 圆角，避免阴影叠加过重。

### 玻璃与渐变规则

不适用，跳过。v1 不使用毛玻璃、渐变或纹理签名处理，保持客服场景的清晰与稳定。

---

## 3. 字体：系统字体的克制配对

标题与正文均采用系统默认中文字体（PingFang SC / Microsoft YaHei），不引入自定义 Web 字体。理由：电信客服用户跨年龄层，系统字体零加载延迟、无 FOUT，契合「清晰胜过炫技」哲学；v1 仅本地 Windows 部署，用户多在 Windows，系统字体已足够。三档用字重区分（600 / 400 / 500）保持一致性。

### 字号阶梯（品牌板须可视化）

| 角色 | 字体族 | 用途 | 样例层级 |
|------|--------|------|---------|
| 标题（Headline） | PingFang SC, -apple-system, "Microsoft YaHei", "Helvetica Neue", sans-serif | 页面标题、Modal 标题、卡片标题 | Display 24px(600) / H1 20px(600) / H2 18px(600) / H3 16px(600) |
| 正文（Body） | PingFang SC, -apple-system, "Microsoft YaHei", "Helvetica Neue", sans-serif | 对话消息、表单、列表、按钮文字 | Body 14px(400) / Body-sm 13px(400) |
| 标签（Label） | PingFang SC, -apple-system, "Microsoft YaHei", "Helvetica Neue", sans-serif | 表单 label、徽章、时间戳、辅助提示 | Caption 12px(500) |

完整字号阶梯（行高）：

| 阶梯 | 字号 | 行高 | 字重 | 用途 |
|------|------|------|------|------|
| Display | 24px | 32px | 600 | 页面主标题（极少用） |
| H1 | 20px | 28px | 600 | 页面标题、Modal 标题 |
| H2 | 18px | 26px | 600 | 卡片标题、区块标题 |
| H3 | 16px | 24px | 600 | 子标题、列表项标题 |
| Body | 14px | 22px | 400 | 正文、对话消息、表单 |
| Body-sm | 13px | 20px | 400 | 表格行、辅助文字 |
| Caption | 12px | 18px | 500 | 标签、时间戳、徽章 |

### 信息层级

标题与正文对比：H1 20px(600) vs Body 14px(400)——字号差 6px + 字重差 200，层级清晰。正文与辅助对比：Body 14px(400) vs Caption 12px(500)——字号差 2px 但字重提升，辅助信息不抢戏但可读。对话消息特殊：用户消息与助理消息字号一致（14px），用气泡颜色与对齐方向区分（左助理右用户，或反之），不靠字号制造层级。

### 字体实现约束（受限运行时须填写）

不适用，跳过。技术栈为 Vue3 + Element Plus（纯 Web，无受限运行时），不引入自定义字体，使用系统字体降级，无加载策略需求。

---

## 4. 层级与深度

层级通过色调叠层而非线框建立。卡片浮于 base 靠阴影，选中靠背景色阶差异，悬停靠浅底色提示——这些手法共同构成「无描边」的视觉分区体系，让界面通透且不杂乱。

* **叠层原则：** 背景层级靠色阶差异（base `Neutral 50` → card `白` → overlay `白 + 强阴影`）；悬浮态用背景色微调（列表行 hover 用 `primary-tint-bg`）；强调态用文字/图标色 + 左侧 3px 色条（选中列表行用 `Primary 500` 色条 + `primary-tint-bg-strong` 背景）。
* **环境阴影：** 阴影规格分 5 档（`shadow-xs` 至 `shadow-lg`），均使用低透明度黑色（0.04–0.1）避免纯黑重影，聚焦态用 Primary 100 环替代默认蓝色 outline。具体：`shadow-xs` `0 1px 2px rgba(0,0,0,0.04)`（卡片基线）、`shadow-sm` `0 1px 3px rgba(0,0,0,0.05), 0 1px 2px rgba(0,0,0,0.03)`（列表行 hover）、`shadow-md` `0 4px 6px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.04)`（下拉、popover）、`shadow-lg` `0 10px 15px rgba(0,0,0,0.1), 0 4px 6px rgba(0,0,0,0.05)`（Modal、弹层）、`shadow-focus` `0 0 0 2px #C9DEFF`（聚焦态环）。
* **幽灵描边兜底：** 输入框默认态用 `1px solid Neutral 300` `#D1D5DB` 细描边作为表单元素标识；聚焦态移除描边改用 `shadow-focus`；错误态移除描边改用 `0 0 0 2px semantic-error 100` `#FFCDD2` 环。卡片、Modal、列表行、侧栏分隔线一律禁用描边，靠阴影与背景色阶分区。

### 叠色对照表（品牌板须可视化）

凡在 §5 组件/状态里复现 ≥2 次的叠色须在此固化；§5 引用 Token 名，禁止仅写 `@ N%` 简写。

| Token | 基准色 | 不透明度 | 预计算 HEX | 用途 |
|-------|--------|---------|-----------|------|
| `primary-tint-bg` | Primary 500 `#1A6FFF` | 3% | `#F4F8FF` | 列表行 hover 背景、文字按钮悬停底、侧栏菜单项 hover |
| `primary-tint-bg-strong` | Primary 500 `#1A6FFF` | 8% | `#E0EBFF` | 选中态背景（列表行、侧栏菜单、图标按钮选中）、徽章 Primary 变体底 |
| `tertiary-tint-bg` | Tertiary 500 `#FF8A3D` | 10% | `#FFF1E5` | 办理类业务强调底、二次确认强调底 |
| `semantic-error-tint-bg` | semantic-error 500 `#E53935` | 8% | `#FCEAEA` | 错误提示底、认证失败提示底、危险图标按钮 hover 底、徽章 Error 变体底 |
| `semantic-success-tint-bg` | semantic-success 500 `#2E7D32` | 8% | `#EBF5EC` | 成功提示底、办理生效通知底、徽章 Success 变体底 |
| `semantic-warning-tint-bg` | semantic-warning 500 `#F9A825` | 10% | `#FFF6E0` | 警告提示底、二次确认 Modal 强调底、徽章 Warning 变体底 |
| `semantic-info-tint-bg` | semantic-info 500 `#0288D1` | 8% | `#E8F4FB` | 系统消息底、Notification 推送底、列表行未读高亮底、徽章 Info 变体底 |
| `neutral-overlay` | Neutral 900 `#111827` | 50% | `#080C14` | Modal 遮罩、全屏加载遮罩 |

预计算方式：`bg = base + (color - base) × opacity`（白底叠加）。

---

## 5. 组件

各组件须有足够细节使品牌板可画出样张。只写通用 UI 原语（atom/molecule），不写页面名、业务字段布局、功能专属复合组件、领域术语、业务状态名。复用叠色引用 §4 Token 名；单次叠色直接写 HEX。

### 按钮与交互（品牌板须可视化）

* **主按钮（Primary）：** 背景 `Primary 500` `#1A6FFF`、文字 `白` `#FFFFFF`、圆角 6px、悬停背景 `Primary 600` `#0D5BE6`、按下背景 `Primary 700` `#0A47B8`、禁用背景 `Neutral 200` `#E5E7EB` 文字 `Neutral 400` `#9CA3AF`。每屏最多 1 个。
* **次按钮（Secondary）：** 背景 `Primary 50` `#E8F2FF`、文字 `Primary 600` `#0D5BE6`、圆角 6px、悬停背景 `primary-tint-bg-strong` `#E0EBFF`、按下背景 `Primary 100` `#C9DEFF`、禁用背景 `Neutral 100` `#F3F4F6` 文字 `Neutral 400`。
* **描边按钮（Outline）：** 背景透明、文字 `Primary 500` `#1A6FFF`、圆角 6px、悬停背景 `primary-tint-bg` `#F4F8FF` 边框 `Primary 500`、按下背景 `primary-tint-bg-strong` `#E0EBFF`、禁用文字 `Neutral 400` 边框 `Neutral 300` `#D1D5DB`。
* **文字按钮（Text）：** 背景透明、文字 `Primary 500` `#1A6FFF`、无圆角、悬停文字 `Primary 600` `#0D5BE6` 背景 `primary-tint-bg` `#F4F8FF`、按下文字 `Primary 700` `#0A47B8`、禁用文字 `Neutral 400`。
* **反色按钮（Inverted）：** 背景 `白` `#FFFFFF`、文字 `Primary 600` `#0D5BE6`、圆角 6px、悬停背景 `Neutral 100` `#F3F4F6`、按下背景 `Neutral 200` `#E5E7EB`、禁用背景 `Neutral 700 @ 50%` 文字 `Neutral 400`。用于深色背景上的主操作（如顶栏登出、深色 Modal 头部关闭）。

尺寸：默认 36px（内边距 12×20）、大号 40px（关键确认如二次确认 Modal）、小号 28px（行内操作）。

### 输入与表单

* **默认态：** 背景 `白` `#FFFFFF`、描边 `1px solid Neutral 300` `#D1D5DB`、文字 `Neutral 800` `#1F2937`、圆角 6px、高度 36px、内边距 8×12、placeholder `Neutral 400` `#9CA3AF`。
* **聚焦态：** 移除描边、外发光 `shadow-focus`（`0 0 0 2px Primary 100` `#C9DEFF`）、文字 `Neutral 800`。
* **错误态：** 移除描边、外发光 `0 0 0 2px semantic-error 100` `#FFCDD2`、文字 `Neutral 800`、错误文案 `semantic-error 500` `#E53935`（字号 12px / 字重 500，输入框下方间距 4px）。
* **禁用态：** 背景 `Neutral 50` `#F9FAFB`、描边 `1px solid Neutral 200` `#E5E7EB`、文字 `Neutral 400`。

表单元素：Label 字号 13px / 字重 500 / `Neutral 700` `#374151`，与输入框间距上 6px；必填星号 `semantic-error 500`；辅助说明字号 12px / `Neutral 500`；Select 同输入框三态，下拉面板 `shadow-md`，选中项背景 `primary-tint-bg-strong` 文字 `Primary 600`；Checkbox/Radio 选中 `Primary 500` 未选中边框 `Neutral 300`；Switch 开启 `Primary 500` 关闭 `Neutral 300`。

### 卡片容器

* 圆角 8px、内边距 16px（默认）/ 24px（宽松 Modal 内容）/ 12px（紧凑列表卡片）、阴影 `shadow-xs`（默认浮于 base）、悬停升 `shadow-sm`（若可交互）、背景 `白` `#FFFFFF`、描边无。
* **静态卡片：** 默认规格无悬停。
* **可交互卡片：** 悬停 `shadow-sm`、光标 pointer。
* **嵌套卡片：** 内层去阴影改用 `Neutral 50` `#F9FAFB` 底 + 6px 圆角。
* **Modal 弹层卡片：** 圆角 12px、阴影 `shadow-lg`、内边距 24px、含 Header（标题 + 关闭按钮）+ Body + 可选 Footer，Header 与 Body 间用 `1px solid Neutral 100` `#F3F4F6` 极淡分区线。

### 列表行

* 行高 48px（默认）/ 56px（宽松含多行）/ 36px（紧凑选项列表）、行间距无、分隔方式底部 `1px solid Neutral 100` `#F3F4F6`、背景 `白`、内边距 12×16。
* **默认：** 背景 `白`、文字 `Neutral 800` `#1F2937`。
* **悬停：** 背景 `primary-tint-bg` `#F4F8FF`、文字 `Neutral 800`。
* **选中：** 背景 `primary-tint-bg-strong` `#E0EBFF`、文字 `Primary 600` `#0D5BE6`、左侧 3px `Primary 500` `#1A6FFF` 色条。
* **高亮（未读）：** 背景 `semantic-info-tint-bg` `#E8F4FB`、文字 `Neutral 800`、无色条（与选中态区分）。
* **禁用：** 背景 `Neutral 50` `#F9FAFB`、文字 `Neutral 400` `#9CA3AF`。

### 导航

* **顶栏：** 高度 56px、背景 `白`、底部 `1px solid Neutral 100` 极淡分隔线、内边距 0×24、无阴影（结构不浮起）。
* **侧栏：** 宽度 200px（展开）/ 64px（折叠）、背景 `白`、右侧 `1px solid Neutral 100`、内边距 12×8、菜单项高度 40px 圆角 6px。菜单项态：默认透明背景文字 `Neutral 700`、悬停 `primary-tint-bg` `#F4F8FF` 文字 `Neutral 800`、选中 `primary-tint-bg-strong` `#E0EBFF` 文字 `Primary 600`（不用色条，靠背景与文字色）、禁用文字 `Neutral 400`。
* **底栏 Tab：** 高度 48px、背景 `白`、顶部 `1px solid Neutral 100`、图标 24px 描边 1.5px。态：默认图标 `Neutral 500` 文字 `Neutral 500`、选中图标 `Primary 500` `#1A6FFF` 文字 `Primary 500`、禁用 `Neutral 400`。

### 搜索框

顶栏内嵌全局搜索（仅坐席工作台启用，用户端无全局搜索）。

* **搜索框形态：** 宽度 240px（折叠）/ 320px（展开聚焦平滑过渡）、高度 32px（小于默认 36px 适配顶栏）、圆角 16px（胶囊形）、背景 `Neutral 100` `#F3F4F6`、默认无描边、聚焦态背景 `白` + `shadow-focus`、左侧搜索图标 16px `Neutral 500` 与文字间距 8px、placeholder `Neutral 400` 字号 13px、文字 `Neutral 800` 字号 13px。
* **下拉结果面板：** 宽度 320px、背景 `白`、阴影 `shadow-md`、圆角 8px、与搜索框间距 4px。结果分组标题 12px / 字重 500 / `Neutral 500`；结果项复用 §5.4 列表行规格（行高 48px，默认/悬停/选中三态）。空结果居中文字「无匹配结果」14px / `Neutral 400`。

### 状态徽章

* **组件形态：** 圆角 4px（微圆角）、内边距 2×8、字号 12px（Caption 级）、字重 500、字体族 Label、行高 16px、描边无（用背景色 + 文字色）。
* **变体：**
  - Neutral：背景 `Neutral 100` `#F3F4F6`、文字 `Neutral 700` `#374151`（中性状态）
  - Primary：背景 `primary-tint-bg-strong` `#E0EBFF`、文字 `Primary 700` `#0A47B8`（主品牌关联状态）
  - Success：背景 `semantic-success-tint-bg` `#EBF5EC`、文字 `semantic-success 700` `#1B5E20`（成功语义）
  - Warning：背景 `semantic-warning-tint-bg` `#FFF6E0`、文字 `semantic-warning 700` `#F57F17`（警告语义）
  - Error：背景 `semantic-error-tint-bg` `#FCEAEA`、文字 `semantic-error 700` `#B71C1C`（错误语义）
  - Info：背景 `semantic-info-tint-bg` `#E8F4FB`、文字 `semantic-info 700` `#01579B`（信息语义）
* **通用样例：** 成功语义徽章——背景 `semantic-success-tint-bg` `#EBF5EC`、文字 `semantic-success 700` `#1B5E20`、内容「示例」。

### 图标按钮

* **尺寸：** 32×32（默认）/ 40×40（大，顶栏主操作）/ 24×24（紧凑，行内）；图标尺寸 16px / 20px / 12px；描边粗细 1.5px（线性图标，与底栏 Tab 一致）；圆角 6px（方形）/ 16px（圆形如头像操作）；背景透明、描边无（默认）。
* **默认态五态：**
  - 默认：背景透明、图标 `Neutral 600` `#4B5563`
  - 悬停：背景 `Neutral 100` `#F3F4F6`、图标 `Neutral 800` `#1F2937`
  - 按下：背景 `Neutral 200` `#E5E7EB`、图标 `Neutral 800`
  - 选中：背景 `primary-tint-bg-strong` `#E0EBFF`、图标 `Primary 600` `#0D5BE6`（与列表行选中一致）
  - 禁用：背景透明、图标 `Neutral 400` `#9CA3AF`
* **特殊变体：**
  - 主色图标按钮：背景 `Primary 500`、图标 `白`、悬停 `Primary 600`（如发送消息）
  - 危险图标按钮：默认 `Neutral 600`、悬停背景 `semantic-error-tint-bg` `#FCEAEA` 图标 `semantic-error 500` `#E53935`（如删除）
  - 底栏 Tab 图标按钮：与 §5.5 导航底栏 Tab 一致，默认 `Neutral 500` 选中 `Primary 500`，图标 24px + 40×40 热区
* **Tooltip：** 悬停 500ms 后显示、背景 `Neutral 800` `#1F2937`、文字 `白` 字号 12px、圆角 4px、内边距 4×8、与按钮间距 4px。

### 空状态

* **结构：** 插画/图标 64×64 线性描边 1.5px 色 `Neutral 300` `#D1D5DB`（弱化）、主文案字号 14px / 字重 500 / `Neutral 700` `#374151` 居中、辅助文案字号 13px / 字重 400 / `Neutral 500` `#6B7280` 居中与主文案间距 8px、CTA 按钮可选（主或描边）与主文案间距 16px 尺寸 36px、整体垂直水平居中、容器内边距 48×24。
* **变体：**
  - 无数据空状态：插画 + 主文案（通用 pattern，不写具体业务）+ 可选辅助文案
  - 无结果空状态：插画 + 主文案 + 可选 CTA（如清除筛选）
  - 错误空状态：插画色 `semantic-error 300` `#FFCDD2`、主文案 `semantic-error 700` `#B71C1C`、辅助文案 `Neutral 500`、CTA「重试」用主按钮
  - 首次使用空状态：插画 + 主文案 + 辅助文案 + CTA「立即开始」用主按钮
* **CTA 规则：** 仅一个操作用主按钮；有次要操作用主按钮 + 描边按钮；无操作仅插画 + 文案。

### Loading

电信客服场景大量异步等待（LLM 流式、WS 连接、查询加载、办理执行），Loading 是高频组件。

* **Spinner：** 尺寸 16px（行内）/ 24px（按钮内）/ 32px（区块）、形态圆形旋转 2 段弧、颜色 `Primary 500` `#1A6FFF`（默认）/ `白`（主按钮内）/ `Neutral 400`（弱化）、描边 2px / 2.5px / 3px、动画 1s 线性循环顺时针。用于按钮提交、行内等待、小型区块。
* **骨架屏：** 背景 `Neutral 100` `#F3F4F6`、高光 `Neutral 200` `#E5E7EB`（1.5s 从左到右扫描 ease-in-out）、圆角与被占位组件一致（卡片 8px / 文本条 4px / 头像圆形）。形态：卡片骨架矩形 100%×120px 圆角 8px；文本条骨架高度 12px 宽度自适应（短 60% / 中 80% / 长 100%）圆角 4px 间距 8px；头像骨架 40×40 圆形；列表行骨架行高 48px 左侧头像 + 右侧两行文本条。用于列表加载、详情页加载、卡片区块加载。
* **信号脉冲（签名动效）：** 用于 LLM 流式输出等待首字（WS 已建立但 token 未到）。形态 3 个圆点依次脉动、圆点 6px 间距 4px、颜色 `Primary 500` `#1A6FFF`、动画 1.4s 缩放 + 透明度循环（0.3 → 1.0 → 0.3）依次延迟 0.2s。用于对话气泡内「助理正在输入」、流式响应等待。呼应 §1 创意北极星「Signal」。
* **全屏加载：** 居中 spinner 32px `Primary 500`、背景半透明遮罩 `neutral-overlay` `#080C14`。用于页面路由切换、鉴权中。

---

## 6. 宜忌

### 应当：

* **应当用色调叠层与背景色阶分隔区块** — 卡片浮于 base 用 `shadow-xs`，选中用 `primary-tint-bg-strong`，悬停用 `primary-tint-bg`（§4 叠色对照表）。
* **应当聚焦态用环不用边框** — 输入框聚焦用 `shadow-focus`（§4），错误态用 `semantic-error 100` 环（§5.2）。
* **应当用信号脉冲表达 LLM 等待** — 对话气泡内首字等待用信号脉冲（§5.10），呼应创意北极星「Signal」。
* **应当每屏主按钮最多 1 个** — 主操作用主按钮，次操作用次/描边按钮（§5.1）。
* **应当列表选中态用左侧色条 + 背景色** — 不用整行边框，侧栏除外（§5.4 / §5.5）。

### 禁止：

* **禁止用实线边框分隔区块** — 卡片、列表行、Modal、侧栏分隔线用 `1px Neutral 100` 极淡线或阴影，不用 `1px Neutral 300` 实线边框（§2 无描边规则）。
* **禁止错误态用临时 HEX** — 错误态必须引用 `semantic-error` Token，禁止裸写 `#E53935`（§5.2 / §5.7）。
* **禁止裸写叠色简写** — `primary @ 8%` 等须引用 §4 Token 名 `primary-tint-bg-strong`，禁止裸写百分比（§4 / §5）。
* **禁止徽章写业务状态名或状态色映射** — §5.7 仅写组件形态与通用样例，业务状态映射在实现规划阶段处理（§5.7）。
* **禁止自定义字体或加载 Web 字体** — 用系统字体 PingFang SC / Microsoft YaHei，避免 FOUT 影响首屏（§3）。
