# 电信客服 Agent v1 — PRD

> UI 模式：`spec-driven`（UI 设计描述为编码唯一权威来源，不规划设计稿）
> 端：`customer-web`（用户端）、`agent-console`（坐席工作台）
> 领域词汇与业务规则见 `CONTEXT.md`；架构决策见 `docs/adr/`；品牌视觉见 `docs/design/DESIGN.md`

## 问题陈述

电信用户带着具体问题而来——查话费、办套餐、报故障、投诉咨询——但传统客服渠道存在三类痛点：

1. **入口分散、找路成本高**：查询、办理、报修分布在不同入口与 IVR 菜单层级，用户需在多选项间反复试探，焦虑场景下三秒内找不到下一步是常态。
2. **办理不可逆、风险高**：套餐变更、停机保号、增值业务订退等写入操作一旦误办难以回退；纯自动办理缺乏身份复核，会话被劫持后将造成资损与合规风险。
3. **自动服务与人工服务割裂**：LLM 助理能处理大部分咨询与查询，但超出能力范围、合规争议、负面情绪场景需人工介入；现有系统在自动与人工之间缺乏平滑的上下文交接，用户需重复陈述问题。

访客（未认证用户）只能做通用咨询，无法查询或办理与号码绑定的业务；客户（已认证用户）需要安全的查询与办理通道；坐席需要高效接手转接会话并跟踪工单。本 PRD 覆盖 v1 范围内的全部业务能力。

## 解决方案

构建一个 LLM 主导多轮对话的电信客服 Agent 系统：

- **助理（Assistant）** 承担主对话，通过 tools 调用四类业务能力——查询类（只读，认证后直接返回）、办理类（写入/不可逆，经二次确认后创建 Ticket 入队，执行前再要求服务密码复核）、通用咨询类（无需认证，访客可用）、工单类（故障报修等需跟踪事项）。
- **坐席（Human Agent）** 通过工作台接手 Handoff 转接的会话，处理超出助理能力、合规争议、负面情绪等场景；助理退至后台协同，坐席可显式转回。
- **工单（Ticket）** 统一模型承载办理类与工单类业务，按类型走不同状态机，状态变化通过 Notification 推送给用户。
- **会话状态机** 管理 Unauthenticated → Authenticated → In-Progress → Handed-off → Closed 全生命周期，服务密码认证是 Visitor 升格 Customer 的凭证。
- **离线兜底**：非坐席服务时间或全忙时，助理告知用户并创建回呼请求 Ticket，不强制结束会话。

前端分两端：用户端以对话为主入口，底栏 Tab 切换会话/工单/我的；坐席工作台以侧栏导航待接入队列、进行中会话、工单管理。视觉遵循「Signal」创意北极星——清晰胜过炫技，专业稳定克制温度，信号脉冲作为签名动效贯穿 LLM 等待场景。

## 用户故事

### 用户端 customer-web

US-1：作为访客，我想要在对话中咨询套餐介绍与对比、网络覆盖、营业厅地址，以便无需认证即可获取公开信息。

US-2：作为访客，我想要通过手机号 + 服务密码认证升格为客户，以便查询和办理与号码绑定的业务。

US-3：作为客户，我想要在对话中查询话费余额，以便了解当前账户状态。

US-4：作为客户，我想要查询当前套餐详情，以便了解已订套餐内容与资费。

US-5：作为客户，我想要查询通话与流量使用量，以便掌握用量情况。

US-6：作为客户，我想要查询合约到期时间，以便规划续约或变更。

US-7：作为客户，我想要查询已订购增值业务，以便管理订阅。

US-8：作为客户，我想要发起套餐变更并经二次确认，以便安全完成不可逆变更。

US-9：作为客户，我想要订退增值业务并经二次确认，以便管理增值订阅。

US-10：作为客户，我想要办理停机保号并经二次确认，以便暂停服务保留号码。

US-11：作为客户，我想要充值缴费并经二次确认，以便补缴话费恢复服务。

US-12：作为客户，我想要在办理工单执行前再次输入服务密码复核，以便防止会话被劫持后办理不可逆业务。

US-13：作为客户，我想要创建故障报修工单，以便跟踪维修进度。

US-14：作为客户，我想要查看我的工单状态与站内通知，以便了解办理与报修进度。

US-15：作为客户，我想要在对话中显式请求转人工，以便获得人工帮助。

US-16：作为客户，我想要在 Handed-off 状态下与坐席对话，以便获得人工服务且不必重复陈述问题。

US-17：作为客户，我想要查看会话历史与账号信息，以便回顾既往交互。

US-18：作为客户，我想要在会话超时后重新进入新会话，以便继续获取服务而不丢失上下文记忆。

### 坐席端 agent-console

US-19：作为坐席，我想要登录工作台，以便接入服务接单。

US-20：作为坐席，我想要查看待接入会话队列，以便按序接入 Handoff 会话。

US-21：作为坐席，我想要接入转接会话并查看会话历史与客户资料，以便快速了解上下文不重复询问。

US-22：作为坐席，我想要在 Handed-off 状态下与用户对话，以便处理超出助理能力的场景。

US-23：作为坐席，我想要创建工单，以便跟踪需后续处理的事项。

US-24：作为坐席，我想要处理工单（派单、关闭、取消），以便推进工单状态机。

US-25：作为坐席，我想要处理待执行办理工单并在执行前复核服务密码，以便安全执行不可逆业务。

US-26：作为坐席，我想要将会话转回助理，以便恢复自动服务。

US-27：作为坐席，我想要查看并筛选工单列表，以便管理多个工单。

US-28：作为坐席，我想要查看工单详情与审计日志，以便合规留痕与追溯。

US-29：作为坐席，我想要查看回呼请求工单（离线兜底），以便在服务时间联系用户。

US-30：作为坐席，我想要设置自身状态（在线/离线/小休），以便管理接单能力。

## UI 与设计要求

**UI 模式**：`spec-driven`（来源：`docs/design/DESIGN.md` 文首 `> UI 模式：spec-driven`）。UI 设计描述为编码的唯一权威来源（SSOT），不规划设计稿；状态变体一律写入各页 UI 设计描述的变体段。

**文档分工**：领域术语与业务规则 → `CONTEXT.md`（PRD 只用其词汇）；架构/技术栈 → `docs/adr/`；品牌视觉（色板、字体、通用 UI 原语、宜忌）→ `docs/design/DESIGN.md`（本 PRD 仅引用 Token/组件名，不重写规格）；功能页面规格 → 本 PRD 各页 UI 设计描述。

**术语约定**：`page-id`（kebab-case 机器标识，用于路由/清单键/Issue 绑定）；页面标题（人类可读短名）。

### 状态策略

| 状态 | 处理方式 |
|---|---|
| 加载中 | 对话流 LLM 等待首字用**信号脉冲**（§5 Loading 签名动效，3 圆点 `Primary 500` 脉动）；列表/详情/卡片用骨架屏（§5，`Neutral 100` 底 + `Neutral 200` 高光扫描）；按钮提交用按钮内 spinner（§5，`Primary 500`/白）；路由切换与鉴权用全屏 spinner（§5，`neutral-overlay` 遮罩 + 32px spinner） |
| 空状态 | 工单列表/队列无数据用 §5 empty-state 插画（64px 线性 `Neutral 300`）+ 主辅文案居中；对话空状态用问候语气泡（助理先发问候）替代插画；无搜索结果用「无匹配结果」14px `Neutral 400` 居中 |
| 错误 | 输入框错误态移除描边改用 `semantic-error 100` 外发光环 + `semantic-error 500` 文案（§5 输入）；办理失败/查询失败用 Error 徽章 + 重试主按钮（§5 空状态错误变体）；WS 断线用顶栏条（`semantic-error-tint-bg` 底）提示「连接已断开，正在重连」 |
| 禁用 | 主按钮禁用态 `Neutral 200` 底 + `Neutral 400` 文字（§5 按钮）；未认证时办理入口禁用并提示「请先认证」；服务密码复核提交中按钮禁用 + spinner |
| 上传中 | 表单提交按钮内 spinner 替换文字，按钮禁用；服务密码输入提交期间输入框禁用 + 按钮禁用 spinner |
| 搜索展开 | 坐席工作台顶栏全局搜索聚焦时宽度 240px→320px 平滑过渡，下拉结果面板 `shadow-md`（§5 搜索框） |
| Handoff 等待 | 用户端：顶栏出现「正在为您转接坐席…」`semantic-info-tint-bg` 条 + 信号脉冲；坐席端：待接入队列项高亮 `semantic-info-tint-bg` 未读态 |

### 页面清单

清单顺序：按 `platform-id` 分组，每组第一条为该端 `app-shell`，其后为功能页。spec-driven 模式无默认态设计稿列。

#### customer-web 端

**`app-shell`（用户端整体框架）**
- **端 / 运行环境**：customer-web / 浏览器（Vue3 + Element Plus）
- **page-id**：`app-shell`
- **页面标题**：用户端框架
- **主任务**：定义用户端全局导航壳层，不承载具体业务任务
- **覆盖的用户故事**：—（壳层支撑 US-14/US-17 导航与布局）
- **DESIGN 复用**：§5 顶栏、§5 底栏 Tab、§4 叠色、§5 状态徽章
- **UI 设计描述**：整体框架页，定义用户端 viewport 分区为三段——顶部 56px 顶栏（背景 `白`，底部 `1px solid Neutral 100` 极淡分隔线，无阴影），含左侧品牌标识（电信蓝 `Primary 500` 文字 Logo）、中部会话标题（Body 14px `Neutral 800`，随当前会话状态变化：未认证显示「在线咨询」、已认证显示号码脱敏、Handed-off 显示「坐席服务中」）、右侧会话状态徽章（Neutral 变体「访客」/ Primary 变体「已认证」/ Info 变体「转接中」）；中部内容区 flex 填充，背景 `surface-base` `Neutral 50`，默认左右页边距 0（对话流全宽，其他页 24px）；底部 48px 底栏 Tab（背景 `白`，顶部 `1px solid Neutral 100`），三个 Tab「会话」「我的工单」「我的」，图标 24px 描边 1.5px，默认 `Neutral 500`，选中 `Primary 500` 图标+文字。壳层变体：`auth`（服务密码认证）**完全脱离壳层**，无顶栏无底栏，全屏独立任务页；`chat` 隐藏底栏 Tab 之外的 chrome 不变。功能页引用：所有 customer-web 功能页继承本壳层，仅描述内容区差异。

**`auth`（服务密码认证）**
- **端 / 运行环境**：customer-web / 浏览器
- **page-id**：`auth`
- **页面标题**：服务密码认证
- **主任务**：访客通过手机号 + 服务密码认证升格为客户
- **覆盖的用户故事**：US-2
- **DESIGN 复用**：§5 输入与表单（默认/聚焦/错误/禁用四态）、§5 按钮主/次、§5 卡片容器（Modal 弹层卡片）、§5 Loading
- **UI 设计描述**：**脱离 app-shell**（无顶栏无底栏），全屏独立任务页，背景 `surface-base`。垂直水平居中一张 Modal 弹层卡片（圆角 12px、`shadow-lg`、内边距 24px、宽 400px），卡片内自上而下：品牌标识（电信蓝 Logo + 「电信客服」H2 18px `Neutral 800` 600 字重，间距下 8px）、辅助文案（Body-sm 13px `Neutral 500`「请输入服务密码以查询和办理业务」，间距下 24px）、手机号输入框（Label「手机号」13px `Neutral 700` + 必填星号 `semantic-error 500`，输入框默认态 `1px Neutral 300` 描边，聚焦态 `shadow-focus`，placeholder「请输入 11 位手机号」）、服务密码输入框（同上规格，type=password，placeholder「请输入服务密码」，右侧眼睛图标按钮切换明文）、主按钮「认证」（40px 大号，`Primary 500` 底白字，宽度 100%，间距上 16px）、文字按钮「暂不认证，先咨询」（居中，`Primary 500` 文字，间距上 12px，返回会话保持访客身份）。交互：输入框聚焦移除描边改外发光环；认证失败时两输入框错误态 `semantic-error 100` 环 + 下方错误文案 `semantic-error 500`「手机号或服务密码错误」；提交中主按钮禁用 + 白 spinner + 文字「认证中…」。变体段：错误变体如上；禁用变体——手机号未满 11 位时主按钮禁用 `Neutral 200` 底。空状态不适用。

**`chat`（主会话）**
- **端 / 运行环境**：customer-web / 浏览器
- **page-id**：`chat`
- **页面标题**：客服会话
- **主任务**：用户与助理/坐席多轮对话，完成咨询、查询、办理发起、转接
- **覆盖的用户故事**：US-1、US-3~US-13、US-15、US-16、US-18
- **DESIGN 复用**：§5 卡片（气泡）、§5 按钮主/次/文字、§5 输入与表单、§5 Loading（信号脉冲）、§5 状态徽章、§4 叠色（`primary-tint-bg`/`tertiary-tint-bg`/`semantic-info-tint-bg`/`semantic-warning-tint-bg`）
- **UI 设计描述**：继承 customer-web **app-shell**，顶栏选中状态随会话状态变化（壳层定义），底栏 Tab 选中「会话」；本页仅描述内容区。内容区分上下两段：上方对话流区（flex 填充，可滚动，背景 `surface-base`，内边距 16px），消息气泡自上而下排列——助理消息左对齐（气泡背景 `白` `shadow-xs` 圆角 8px，左上角直角，文字 Body 14px `Neutral 800`，最大宽 70%）、用户消息右对齐（气泡背景 `Primary 500` 文字白，圆角 8px 右上角直角）、系统消息居中（无气泡，整行 `semantic-info-tint-bg` 底圆角 4px 内边距 4×8，Caption 12px `semantic-info 700`，如「会话已转接给坐席」）、坐席消息左对齐（与助理同形，但头像区分坐席标识）；助理正在生成时在助理气泡位置显示**信号脉冲**（3 圆点 `Primary 500` 脉动）。对话流顶部历史消息加载完毕显示「以上是历史消息」分隔。下方输入区（固定底部，背景 `白`，顶部 `1px solid Neutral 100` 极淡分隔线，内边距 12×16）：左侧 textarea（默认态 `1px Neutral 300` 描边圆角 6px，聚焦 `shadow-focus`，placeholder「请描述您的问题…」，支持回车发送 Shift+回车换行）、右侧发送主色图标按钮（背景 `Primary 500` 图标白 32×32 圆角 6px，禁用态 `Neutral 200` 底）。对话流内嵌三类 Modal/条：（1）**二次确认 Modal**——助理发起办理类后弹出，Modal 弹层卡片（圆角 12px `shadow-lg`），Header「办理确认」H3 16px + 关闭图标按钮，Body 含业务影响结构化展示（套餐对比/生效时间/合约影响/费用变化，用嵌套卡片 `Neutral 50` 底圆角 6px 分块，关键费用变化用 `tertiary-tint-bg` 底强调），Footer 主按钮「确认办理」（大号 40px，`Primary 500`）+ 描边按钮「取消」；（2）**服务密码复核 Modal**——办理 Ticket 执行前弹出，Modal 卡片含「请再次输入服务密码以完成办理」Body + 服务密码输入框 + 主按钮「确认执行」+ 文字按钮「取消」，强调底用 `semantic-warning-tint-bg`；（3）**Handoff 提示条**——转接触发时对话流内出现系统消息 + 顶栏徽章变 Info「转接中」，等待坐席接入时显示信号脉冲。变体段：空状态——新会话助理先发问候气泡「您好，我是电信客服助理，请问有什么可以帮您？」；错误变体——发送失败时用户气泡右上角 Error 图标按钮 + 「重发」文字按钮；禁用变体——Handed-off 等待坐席接入时输入框禁用 + placeholder「正在为您转接坐席…」；加载变体——历史消息滚动加载顶部骨架屏。

**`tickets`（我的工单）**
- **端 / 运行环境**：customer-web / 浏览器
- **page-id**：`tickets`
- **页面标题**：我的工单
- **主任务**：客户查看本人工单状态与站内通知
- **覆盖的用户故事**：US-14
- **DESIGN 复用**：§5 列表行、§5 状态徽章、§5 卡片容器、§5 空状态、§5 Loading（骨架屏）
- **UI 设计描述**：继承 customer-web **app-shell**，底栏 Tab 选中「我的工单」，顶栏标题「我的工单」（H1 20px `Neutral 800` 600）。内容区背景 `surface-base`，内边距 24px。顶部通知预览条（若有未读 Notification，整宽 `semantic-info-tint-bg` 底圆角 8px 卡片，Caption 12px `semantic-info 700` 文案 + 时间，可点击跳转对应工单，间距下 16px）。下方工单列表（可滚动），每行独立列表行（行高 56px 宽松含多行，背景 `白`，底部 `1px solid Neutral 100` 极淡分隔，内边距 12×16，悬停 `primary-tint-bg`，点击展开详情）：左侧工单类型图标（办理类/工单类区分，16px `Neutral 600`）+ 主文案（工单类型名 + 简述，H3 16px `Neutral 800`）+ 辅助文案（创建时间 Caption 12px `Neutral 500`），右侧状态徽章（按 Ticket 状态机映射：待执行/待派单→Warning 变体、执行中/处理中→Info 变体、已生效/已关闭→Success 变体、已失败→Error 变体、已取消→Neutral 变体）。点击列表行展开内联嵌套卡片（`Neutral 50` 底圆角 6px，无阴影）显示工单详情（内容摘要、状态流转时间线、关联通知），再次点击收起。变体段：空状态——无工单时居中 §5 empty-state 插画 + 主文案「暂无工单」+ 辅助文案「办理业务或报修后将在此显示」；加载变体——列表骨架屏（行高 56px 左侧图标 + 右侧两行文本条）；未认证变体——显示空状态主文案「请先认证查看工单」+ 主按钮「去认证」跳转 `auth`。

**`profile`（我的）**
- **端 / 运行环境**：customer-web / 浏览器
- **page-id**：`profile`
- **页面标题**：我的
- **主任务**：查看账号信息、会话历史、退出登录
- **覆盖的用户故事**：US-17
- **DESIGN 复用**：§5 卡片容器、§5 列表行、§5 按钮文字/反色、§5 空状态
- **UI 设计描述**：继承 customer-web **app-shell**，底栏 Tab 选中「我的」，顶栏标题「我的」（H1 20px `Neutral 800` 600）。内容区背景 `surface-base`，内边距 24px。顶部账号卡片（圆角 8px `shadow-xs` 白底，内边距 16px）：左侧头像占位（40×40 圆形 `primary-tint-bg-strong` 底 + 首字母 `Primary 700`）+ 右侧号码脱敏（H3 16px `Neutral 800`）+ 状态徽章（已认证 Primary 变体/访客 Neutral 变体）+ 当前套餐简述（Body-sm 13px `Neutral 500`）。账号卡片下间距 16px 为「会话历史」区块标题（H2 18px `Neutral 800` 600，间距下 12px）+ 会话历史列表（每行列表行 48px，显示会话起止时间 + 末条消息预览 Body-sm 13px `Neutral 500` 截断 + 状态徽章 Closed→Neutral，点击进入历史会话只读视图）。底部固定区退出登录按钮（反色按钮，`白` 底 `Primary 600` 文字，因置于浅底），间距上 24px。变体段：访客空状态——账号卡片显示「访客身份」+ 主按钮「去认证」；会话历史空状态——居中 §5 empty-state 插画 + 主文案「暂无历史会话」。

#### agent-console 端

**`app-shell`（坐席工作台整体框架）**
- **端 / 运行环境**：agent-console / 浏览器（Vue3 + Element Plus）
- **page-id**：`app-shell`
- **页面标题**：坐席工作台框架
- **主任务**：定义工作台全局导航壳层，不承载具体业务任务
- **覆盖的用户故事**：—（壳层支撑 US-19/US-30 状态切换与导航）
- **DESIGN 复用**：§5 顶栏、§5 侧栏、§5 搜索框、§5 图标按钮、§4 叠色
- **UI 设计描述**：整体框架页，定义坐席工作台 viewport 分区为三段——顶部 56px 顶栏（背景 `白`，底部 `1px solid Neutral 100` 极淡分隔线，内边距 0×24），自左向右：品牌标识（电信蓝 Logo + 「客服工作台」H3 16px `Neutral 800` 600）、全局搜索框（胶囊形 32px 高，背景 `Neutral 100`，聚焦态背景 `白` + `shadow-focus`，宽度 240px→320px 展开，左侧搜索图标 16px `Neutral 500`，placeholder「搜索会话/工单/客户」，下拉结果面板 `shadow-md`，仅工作台启用）、右侧坐席状态切换（图标按钮 40×40 + 状态文字，在线 `semantic-success 500`/小休 `semantic-warning 500`/离线 `Neutral 500`，点击下拉切换）、坐席头像 + 姓名（Body 14px `Neutral 800`）+ 登出反色图标按钮；左侧 200px 侧栏（背景 `白`，右侧 `1px solid Neutral 100`，内边距 12×8），菜单项高度 40px 圆角 6px，自上而下「待接入」「进行中」「工单管理」「历史会话」，默认透明背景文字 `Neutral 700`，悬停 `primary-tint-bg` 文字 `Neutral 800`，选中 `primary-tint-bg-strong` 文字 `Primary 600`（不用色条靠背景与文字色），待接入项右侧未读计数徽章（Error 变体 `semantic-error-tint-bg` 底 `semantic-error 700` 文字）；右侧内容区 flex 填充，背景 `surface-base`，默认页边距 24px。壳层变体：`login`（坐席登录）**完全脱离壳层**，无顶栏无侧栏全屏独立页。功能页引用：所有 agent-console 功能页继承本壳层，仅描述内容区差异与侧栏选中项。

**`login`（坐席登录）**
- **端 / 运行环境**：agent-console / 浏览器
- **page-id**：`login`
- **页面标题**：坐席登录
- **主任务**：坐席登录工作台
- **覆盖的用户故事**：US-19
- **DESIGN 复用**：§5 输入与表单、§5 按钮主、§5 卡片容器（Modal 弹层卡片）、§5 Loading
- **UI 设计描述**：**脱离 app-shell**（无顶栏无侧栏），全屏独立任务页，背景 `surface-base`。垂直水平居中 Modal 弹层卡片（圆角 12px `shadow-lg` 内边距 24px 宽 400px），卡片内自上而下：品牌标识（电信蓝 Logo + 「客服工作台」H2 18px `Neutral 800` 600，间距下 24px）、坐席工号输入框（Label「工号」+ 必填星号，默认态 `1px Neutral 300` 描边，聚焦 `shadow-focus`）、密码输入框（type=password，右侧眼睛图标切换明文）、主按钮「登录」（40px 大号 `Primary 500` 底白字，宽度 100%，间距上 16px）。交互：输入框聚焦移除描边改外发光环；登录失败两输入框错误态 + 错误文案 `semantic-error 500`「工号或密码错误」；提交中主按钮禁用 + 白 spinner + 「登录中…」。变体段：错误变体如上；禁用变体——工号或密码为空时主按钮禁用。空状态不适用。

**`queue`（待接入队列）**
- **端 / 运行环境**：agent-console / 浏览器
- **page-id**：`queue`
- **页面标题**：待接入队列
- **主任务**：坐席查看并接入 Handoff 待接入会话
- **覆盖的用户故事**：US-20、US-21、US-29
- **DESIGN 复用**：§5 列表行（高亮未读态）、§5 按钮主/描边、§5 状态徽章、§5 空状态、§5 Loading（骨架屏）、§4 叠色（`semantic-info-tint-bg`）
- **UI 设计描述**：继承 agent-console **app-shell**，侧栏选中「待接入」，顶栏标题「待接入队列」（H1 20px `Neutral 800` 600）。内容区背景 `surface-base`，内边距 24px。顶部统计条（整宽白底 `shadow-xs` 圆角 8px 卡片，内边距 16px）：左侧「待接入 N 单」H3 16px `Neutral 800` + 辅助文案「非服务时间进入队列的会话次日接入」Caption 12px `Neutral 500`，右侧刷新图标按钮。下方待接入会话列表（可滚动），每行列表行（行高 56px 宽松，背景 `白`，底部 `1px Neutral 100` 分隔，内边距 12×16）：新进入项用高亮未读态（背景 `semantic-info-tint-bg` `#E8F4FB`，无色条，与选中态区分），左侧客户标识（访客/客户徽章）+ 主文案（会话起因摘要「用户请求转人工」「故障报修」H3 16px `Neutral 800`）+ 辅助文案（转接原因 Caption 12px `Neutral 500` + 等待时长），右侧主按钮「接入」（28px 小号 `Primary 500`）。点击接入跳转 `active-chat`。回呼请求工单（离线兜底）在本列表底部独立分组（分组标题 Caption 12px `Neutral 500`「回呼请求」），行右侧按钮为描边按钮「拨打」（`Primary 500` 文字）。变体段：空状态——无待接入时居中 §5 empty-state 插画 + 主文案「暂无待接入会话」+ 辅助文案「有新转接会话将在此显示」；加载变体——列表骨架屏；全部忙线变体——顶部统计条辅助文案改 `semantic-warning 700`「当前所有坐席忙线，新会话进入离线兜底」。

**`active-chat`（进行中会话）**
- **端 / 运行环境**：agent-console / 浏览器
- **page-id**：`active-chat`
- **页面标题**：进行中会话
- **主任务**：坐席在 Handed-off 状态下与用户对话、查看客户资料、操作工单、转回助理
- **覆盖的用户故事**：US-21、US-22、US-23、US-25、US-26
- **DESIGN 复用**：§5 卡片（气泡）、§5 按钮主/次/文字/图标、§5 输入与表单、§5 状态徽章、§5 列表行、§5 Loading（信号脉冲）、§4 叠色
- **UI 设计描述**：继承 agent-console **app-shell**，侧栏选中「进行中」，顶栏含当前会话标题（号码脱敏 H3 16px `Neutral 800`）+ 右侧「转回助理」描边按钮（`Primary 500` 文字，点击将会话转回助理并跳回 `queue`）。内容区左右两栏分布（不对称留白，左密右疏）：左栏对话区（flex 填充约 65% 宽，背景 `surface-base`，内边距 16px）——对话流同 customer-web `chat` 气泡规格（助理/用户/系统/坐席四类消息，助理后台协助起草时坐席可见草稿气泡以 `tertiary-tint-bg` 底区分），底部输入区（固定底，白底 `1px solid Neutral 100` 顶分隔，textarea + 发送主色图标按钮，坐席消息发送后用户视角仍是「客服」）；右栏客户资料侧栏（约 35% 宽，背景 `白` `shadow-xs` 圆角 8px，内边距 16px，可滚动）：顶部客户标识卡（头像 + 号码脱敏 + 状态徽章已认证/访客）、下方分块嵌套卡片（`Neutral 50` 底圆角 6px 无阴影）展示「账户信息」（话费余额 H3 16px `Primary 700` + 套餐名 + 合约到期，敏感数据访问触发审计日志记录）、「当前工单」（列表行 36px 紧凑，每行工单类型 + 状态徽章 + 点击跳 `ticket-detail`）、「转接上下文」（转接原因 + 助理已尝试操作摘要 Body-sm 13px `Neutral 500`）。坐席创建工单通过输入区上方「创建工单」文字按钮弹出 Modal（同二次确认 Modal 规格，含工单类型 Select + 内容 textarea + 主按钮「创建」）。待执行办理工单执行前在右栏「当前工单」中显示主按钮「执行」点击触发服务密码复核 Modal（同 customer-web 规格，要求坐席引导用户再次输入服务密码，复核通过后执行）。变体段：访客变体——右栏客户资料卡显示「访客身份，仅记录联系方式」+ 联系方式字段；加载变体——客户资料加载骨架屏（头像圆形 + 两行文本条）；空状态——无进行中会话时居中 §5 empty-state + 主文案「暂无进行中会话」+ 主按钮「前往待接入队列」。

**`tickets`（工单管理）**
- **端 / 运行环境**：agent-console / 浏览器
- **page-id**：`tickets`
- **页面标题**：工单管理
- **主任务**：坐席查看、筛选、处理工单（派单/关闭/取消/执行复核）
- **覆盖的用户故事**：US-23、US-24、US-25、US-27、US-29
- **DESIGN 复用**：§5 列表行、§5 状态徽章、§5 按钮主/描边/文字、§5 输入与表单（Select）、§5 空状态、§5 Loading（骨架屏）
- **UI 设计描述**：继承 agent-console **app-shell**，侧栏选中「工单管理」，顶栏标题「工单管理」（H1 20px `Neutral 800` 600）。内容区背景 `surface-base`，内边距 24px。顶部筛选栏（白底 `shadow-xs` 圆角 8px 卡片，内边距 12×16）：自左向右工单类型 Select（办理类/工单类/全部）、状态 Select（按状态机各态）、技能组 Select（套餐业务组/故障报修组/投诉处理组）、搜索输入框（同 §5 搜索框规格但宽度 200px）、重置文字按钮。筛选栏下间距 16px 为工单列表（可滚动），每行列表行（行高 56px 宽松，背景 `白`，底部 `1px Neutral 100` 分隔，内边距 12×16，悬停 `primary-tint-bg`，选中 `primary-tint-bg-strong` + 左侧 3px `Primary 500` 色条）：左侧工单 ID Caption 12px `Neutral 500` + 主文案（工单类型 + 内容摘要 H3 16px `Neutral 800`）+ 辅助文案（关联客户号码脱敏 + 创建时间 Body-sm 13px `Neutral 500`），右侧状态徽章（同 customer-web `tickets` 状态映射）+ 行内操作按钮组（按状态显示：待派单→主按钮「派单」、待执行→主按钮「执行」触发服务密码复核 Modal、待确认→描边按钮「关闭」、已派单→文字按钮「查看」跳详情）。变体段：空状态——无工单居中 §5 empty-state + 主文案「暂无工单」+ 辅助文案「调整筛选条件或创建新工单」；加载变体——列表骨架屏；筛选无结果变体——空状态主文案「无匹配工单」+ 描边按钮「清除筛选」。

**`ticket-detail`（工单详情）**
- **端 / 运行环境**：agent-console / 浏览器
- **page-id**：`ticket-detail`
- **页面标题**：工单详情
- **主任务**：坐席查看工单完整信息、状态机流转、审计日志
- **覆盖的用户故事**：US-24、US-28
- **DESIGN 复用**：§5 卡片容器、§5 列表行、§5 状态徽章、§5 按钮主/描边/文字、§5 空状态
- **UI 设计描述**：继承 agent-console **app-shell**，侧栏选中「工单管理」，顶栏含返回图标按钮 + 标题「工单详情」（H1 20px `Neutral 800` 600）+ 右侧状态徽章。内容区背景 `surface-base`，内边距 24px，左右两栏（左主右辅）：左栏（flex 填充约 60%）自上而下：工单基本信息卡片（白底 `shadow-xs` 圆角 8px 内边距 16px，H2 18px 工单类型标题 + Body 14px 内容全文 + Caption 12px 创建时间/创建者/关联客户）、状态流转时间线卡片（白底 `shadow-xs`，标题「状态流转」H3 16px，纵向时间线每节点：状态徽章 + 时间 Caption + 操作人 Body-sm，按状态机顺序排列，当前态高亮 `primary-tint-bg-strong`）、操作区卡片（白底 `shadow-xs`，按当前状态显示可用操作按钮：待派单→主按钮「派单到技能组」+ Select 技能组、待执行→主按钮「执行」触发服务密码复核 Modal、待确认→主按钮「确认关闭」+ 描边按钮「取消工单」、已关闭/已取消→无操作仅文字提示「工单已终结」）；右栏（约 40%）审计日志卡片（白底 `shadow-xs` 圆角 8px 内边距 16px，标题「审计日志」H3 16px `Neutral 800` 600，下方列表行 36px 紧凑，每行：操作类型 Caption 12px `Neutral 500` + 操作详情 Body-sm 13px `Neutral 800` + 时间戳 Caption，按时间倒序，敏感数据访问/服务密码认证/Handoff 等关键操作用 Info 徽章标记）。变体段：空状态——审计日志无记录时居中 Caption「暂无审计记录」；加载变体——时间线与日志骨架屏；已终结变体——操作区无按钮显示「工单已终结」Body 14px `Neutral 500` 居中。

### 用户故事 ↔ 页面映射

| 用户故事编号 | 端 | page-id | 该页承担的故事范围 | UI 设计描述要点 |
|---|---|---|---|---|
| — | customer-web | `app-shell` | —（壳层支撑 US-14/US-17 导航） | 顶栏会话状态徽章 + 底栏 Tab 会话/工单/我的 |
| US-2 | customer-web | `auth` | US-2 认证升格 | 脱离壳层全屏卡片，手机号+服务密码，错误态环 |
| US-1, US-3~US-13, US-15, US-16, US-18 | customer-web | `chat` | 对话咨询/查询/办理发起/二次确认/服务密码复核/转接/Handoff | 对话流气泡+输入区+二次确认 Modal+复核 Modal+Handoff 条+信号脉冲 |
| US-14 | customer-web | `tickets` | US-14 工单状态与通知 | 通知预览条+工单列表+状态徽章+行内展开 |
| US-17 | customer-web | `profile` | US-17 会话历史与账号 | 账号卡片+会话历史列表+退出按钮 |
| — | agent-console | `app-shell` | —（壳层支撑 US-19/US-30 状态与导航） | 顶栏全局搜索+坐席状态切换+侧栏四菜单 |
| US-19 | agent-console | `login` | US-19 登录 | 脱离壳层全屏卡片，工号+密码 |
| US-20, US-21, US-29 | agent-console | `queue` | US-20 队列、US-21 接入、US-29 回呼 | 统计条+待接入列表+接入按钮+回呼分组 |
| US-21, US-22, US-23, US-25, US-26 | agent-console | `active-chat` | US-21 资料、US-22 对话、US-23 建单、US-25 执行复核、US-26 转回 | 左对话区+右客户资料侧栏+创建工单 Modal+执行复核 Modal+转回按钮 |
| US-23, US-24, US-25, US-27, US-29 | agent-console | `tickets` | US-23 建单、US-24 处理、US-25 执行、US-27 筛选、US-29 回呼 | 筛选栏+列表+状态徽章+行内操作+服务密码复核 Modal |
| US-24, US-28 | agent-console | `ticket-detail` | US-24 流转、US-28 审计日志 | 基本信息卡+状态时间线+操作区+审计日志卡 |

映射自检：
- [x] 无孤立故事（US-1~US-30 均已映射）
- [x] 无孤立页面（每页至少支撑一条主路径故事；2 个 `app-shell` 除外）
- [x] 每端有且仅有一个 `app-shell`，排在功能页之前
- [x] `app-shell` UI 设计描述已写壳层分区/导航/内容区/壳层变体，先于功能页
- [x] 功能页首句已声明继承或脱离 `app-shell`
- [x] 每页 UI 设计描述非空且足够详细
- [x] spec-driven：全文无设计稿路径要求

### DESIGN 合规自检

- [x] 未在 PRD 重写色板/字体/Token（仅引用 `Primary 500`、`shadow-focus`、`primary-tint-bg` 等 Token 名）
- [x] 每页布局由 §5 通用原语组合（顶栏/侧栏/Tab/卡片/列表行/按钮/输入/徽章/搜索框/空状态/Loading）
- [x] 导航形态与 §5 一致（顶栏 56px、侧栏 200px、底栏 Tab 48px）
- [x] 空状态/Loading/表单错误态优先复用 §5
- [x] 未违反 §6 宜忌（无实线边框分隔区块，用 `Neutral 100` 极淡线与阴影；聚焦用环不用边框；信号脉冲表达 LLM 等待；每屏主按钮最多 1 个；列表选中用色条+背景）
- [x] 每页均有 UI 设计描述，覆盖框架/层级/组件/交互/变体
- [x] 每端已有 `app-shell`，壳层描述先于功能页；功能页已声明继承/脱离关系
- [x] spec-driven：全文无设计稿，UI 设计描述可直接指导实现
- [x] 受限运行时：不适用（纯 Web Vue3 + Element Plus，DESIGN §3 已注明字体实现约束不适用）

**PRD 末尾摘要**：
- 本计划 **UI 模式**：`spec-driven`
- **页面总数**：11（customer-web 5 含 1 app-shell；agent-console 6 含 1 app-shell）
- **整体框架页**：两端 `app-shell` UI 设计描述已定稿
- **UI 设计描述**：11 页全部已写，无过简页
- **待扩展 DESIGN §5** 项：无（全部复用现有原语）
- `docs/design/DESIGN.md` 就绪情况：已就绪（23059 字节，含 §1-§6 完整规格）

## 实现决策

### 模块划分

模块化单体 FastAPI 应用内部分模块：`auth`（认证与服务密码复核）、`conversation`（会话与消息）、`ticket`（工单状态机）、`agent`（LangChain 助理与 tools）、`ws`（WebSocket 事件）、`scheduler`（APScheduler 异步任务）。模块边界在代码层强制（目录隔离 + import 规范）。

### 认证与会话

- **单因素认证**：手机号 + 服务密码（bcrypt 成本 12），JWT 会话凭证（access token 2h + refresh token 7d）。REST 用 Authorization header，WS 用 JWT 查询参数。
- **办理执行复核（Transaction Re-auth）**：办理类 Ticket 从「待执行」进入「执行中」前，必须要求再次输入服务密码验证通过方可执行，作为单因素认证的补偿控制。
- **已知合规风险**：单因素认证不满足电信/金融监管，v2 应升级双因素（密钥清单预留 `SMS_API_KEY`）。

### API 契约

- **RESTful 端点**（OpenAPI 自动生成）：`/auth/login`（服务密码认证）、`/auth/reauth`（办理执行复核）、`/conversations`（会话 CRUD）、`/conversations/{id}/messages`（消息历史）、`/tickets`（工单 CRUD）、`/tickets/{id}`（工单详情与状态流转）、`/customers/me`（当前客户资料）、`/inquiries/*`（查询类业务能力）、`/transactions/*`（办理类业务能力发起）、`/general-info/*`（通用咨询）、`/agents/login`（坐席登录）、`/agents/status`（坐席状态）、`/agents/queues`（待接入队列）。
- **WebSocket 事件**（`frontend/shared/events.ts` SSOT ↔ `backend/app/ws/events.py` 镜像，CI 校验事件名一致）：`llm.token`（LLM 流式 token）、`message.new`（新消息）、`handoff.start`/`handoff.end`（转接开始/结束）、`ticket.update`（工单状态变化）、`notification.push`（站内通知）、`system.message`（系统消息）、`agent.status`（坐席状态）、`conversation.state`（会话状态机变化）、`second.confirm`（二次确认请求）、`reauth.required`（服务密码复核请求）。

### 会话状态机

`Conversation` 状态：Unauthenticated → Authenticated → In-Progress（等待二次确认）→ Authenticated（Ticket 入队后回退）→ Handed-off（转接）→ Closed。状态变更通过 WS `conversation.state` 事件推送。

### 工单状态机

统一 Ticket 模型（ID、所属 Conversation、创建者、类型、内容、创建时间、状态、关联 Customer 允许 null）：
- **办理类**：Pending → Processing → Effective / Failed / Cancelled
- **工单类**：Pending → Dispatched → In-Progress → Awaiting-confirmation → Closed / Cancelled

### 办理流程

办理类业务一律经二次确认后创建 Ticket 入队，不直接生效：助理发起 → 二次确认 Modal（结构化业务影响）→ 用户确认 → 创建 Ticket（Pending）入队 → 执行前服务密码复核 → Processing → 执行 → Effective/Failed。

### 转接触发

助理在 6 类条件自动触发 Handoff（超出能力范围/办理失败/明确请求/负面情绪/同一意图循环 3 轮/合规风险），无需用户请求。坐席服务时间 1:00-23:00，非服务时间进入待接入队列次日接入；全忙超阈值或非服务时间触发离线兜底（创建回呼请求 Ticket）。

### 知识来源

三类来源 v1 全量启用：结构化数据（DB 套餐/营业厅/资费）、非结构化文档（RAG 政策/规则/手册，sqlite-vec 向量检索）、静态话术（Prompt 问候/转接/合规）。

### 数据库与迁移

SQLAlchemy 2.0 + Alembic，sqlite-vec 向量扩展，SQLite 开启 WAL 模式。所有 schema 变更经 Alembic 迁移，可回滚，向量库 schema 同步纳入 Alembic。

### 任务调度

APScheduler 进程内调度（SQLite 持久化）：Ticket 待执行→执行中触发服务密码复核、会话超时检测、坐席状态监控、离线兜底回呼 Ticket 派单。

### 部署

本地 Windows 裸机，uvicorn 单进程，nginx 托管前端静态产物并反代 `/api` 与 `/ws`，手动启动不自启。Monorepo：`frontend/customer/`、`frontend/agent/`、`frontend/shared/`、`backend/`；前端 pnpm workspace，后端 uv。

## 测试决策

### HTTP 集成 seam

最高层级接缝。通过 pytest + httpx.AsyncClient + in-memory SQLite 测试 REST 端点的请求/响应形状、状态码、鉴权边界。覆盖：服务密码认证成功/失败、办理执行复核、查询类业务能力、办理类发起与二次确认、工单 CRUD 与状态流转、坐席登录与队列。只测外部行为（HTTP 契约），不测 ORM 内部。LLM 相关端点用 FakeListLLM 注入固定响应。

### WS 事件 seam

通过 pytest + httpx WebSocket + FakeListLLM 测试 WebSocket 双向事件：LLM 流式 token 推送、Handoff 开始/结束、Notification 推送、System Message、坐席消息、会话状态机变化、二次确认请求、服务密码复核请求。验证事件契约与 `frontend/shared/events.ts` 镜像一致。

### tool 调用 seam

LangChain tools 作为纯函数测试（与 LLM 调用解耦），用 FakeListLLM 验证对话流与 tool 调用逻辑：查询类四类业务能力返回正确数据、办理类发起二次确认与入队逻辑、通用咨询类 RAG 检索、工单类创建。不验证 LLM 质量（质量评估走线下评估集人工 review）。

### 调度任务 seam

直接调用 APScheduler job 函数（不启调度器）测试：Ticket 待执行→执行中触发服务密码复核、会话超时断开与新 Session 开启、坐席状态监控、离线兜底回呼 Ticket 派单。验证状态机流转与副作用。

### schema 迁移 seam

Alembic 迁移脚本 upgrade/downgrade 可逆性测试，含向量库 schema（sqlite-vec）同步。每个含 schema 变更的 PR 必须带可回滚迁移脚本。

### 前端测试

Vitest + Vue Test Utils 测组件单元（气泡渲染、状态徽章映射、Modal 开关），Playwright 测关键路径 E2E（认证→查询→办理二次确认→工单查看、坐席登录→接入→对话→转回）。Mock LLM 响应保证确定性。

## 范围外

v1 明确排除（见 `CONTEXT.md` § v1 业务范围）：
- 账单明细查询、历史账单、充值记录查询
- 挂失/解挂、注销号码
- 投诉受理（走标准 Ticket 流程，故障报修已覆盖工单类）
- 双因素认证（短信验证码，v2 升级）
- 独立缓存服务（Redis，v1 用 SQLite + 进程内 LRU）
- Docker 容器化部署（v1 本地裸机，v2 上 Linux 补 Dockerfile）
- 多 worker 生产部署（v1 uvicorn 单进程，v2 切 gunicorn + uvicorn worker）
- 短信/推送渠道 Notification（v1 仅站内，预留扩展位）
- LLM 输出质量自动化评估（v1 线下人工 review 评估集）

## 补充说明

**依赖**：
- 后端依赖 LangChain 0.2+（原生支持 sqlite-vec 与 ChatMessageHistory）、FastAPI、SQLAlchemy 2.0、Alembic、APScheduler、passlib[bcrypt]、PyJWT、structlog、prometheus-client。
- 前端依赖 Vue3、Vue Router、Pinia、Vite、Element Plus、openapi-typescript（类型生成）。
- WS 事件契约靠人工镜像维护（`frontend/shared/events.ts` SSOT ↔ `backend/app/ws/events.py`），CI 加脚本校验事件名一致。

**风险**：
- 单因素认证合规风险：服务密码泄露后攻击者可办业务。已通过 Transaction Re-auth 补偿控制缓解，但 v2 须升级双因素。
- SQLite 并发写受限：依赖 WAL 模式与单进程 uvicorn，高并发写入场景需 v2 迁移 PostgreSQL。
- LLM 输出质量无自动化保障：CI 用 Mock LLM 保证确定性，业务逻辑正确性有保障，但 LLM 回答质量需线下评估集人工 review。
- 手动启动无自愈：进程崩溃需人工拉起，v2 应改 NSSM 或 Docker。
- 模块化单体易退化大泥球：必须在代码层强制模块边界（目录隔离 + import 规范）。

**开放问题**：
- 坐席工作台是否需要「历史会话」页的只读详情视图（v1 列表展示，详情可后续补）。
- 信号脉冲动效在低端 Windows 设备上的性能表现需实测。
