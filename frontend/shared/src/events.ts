/**
 * WS 事件契约 SSOT（前端侧）。
 *
 * F0 循环5（issue #2 / PRD 第282行）：
 *   本文件是 WebSocket 事件名的唯一权威来源，与 `backend/app/ws/events.py` 镜像。
 *   CI 通过 `scripts/check_ws_events.py`（后端契约测试驱动）校验双边事件名集合一致。
 *
 * 设计约定：
 *   - 事件名 SSOT 为 `WS_EVENT_NAMES` 常量数组，顺序固定（PRD 出现顺序），驱动
 *     `WsEventName` 联合类型，保证运行时可枚举、编译时可收窄。
 *   - envelope 统一为 `{ event, data }`；payload 字段名沿用后端 Pydantic 直出的
 *     snake_case，避免跨语言映射层（前端消费方直接使用）。
 *   - 各事件 payload 接口在此以 `Record<string, unknown>` 占位，由对应业务垂直切片
 *     （如 conversation 切片补 `message.new`、ticket 切片补 `ticket.update`）在本文件
 *     内细化字段类型——events.ts 始终是文件级 SSOT，不分散到他处。
 */

/** PRD 第282行定义的全部 WS 事件名，顺序固定为 SSOT。 */
export const WS_EVENT_NAMES = [
  'llm.token',
  'message.new',
  'handoff.start',
  'handoff.end',
  'ticket.update',
  'notification.push',
  'system.message',
  'agent.status',
  'conversation.state',
  'second.confirm',
  'reauth.required',
] as const

/** WS 事件名联合类型，由 SSOT 数组派生，禁止手写以防漂移。 */
export type WsEventName = (typeof WS_EVENT_NAMES)[number]

/**
 * 各事件 payload 字段映射。F0 骨架阶段以 `Record<string, unknown>` 占位，
 * 由后续业务切片在本接口内按事件名细化字段类型（仍保持 snake_case）。
 *
 * B2 循环5（issue #7 验收3）：细化 'message.new' | 'system.message'，
 * 与 backend/app/ws/events.py 的 MessageNewPayload / SystemMessagePayload 镜像。
 * B2 循环6（issue #7 验收4）：细化 'conversation.state'，
 * 与 backend/app/ws/events.py 的 ConversationStatePayload 镜像。
 *
 * TODO（后续切片）：
 *   - conversation 切片：细化 'llm.token'
 *   - transaction 切片（B6）：'second.confirm' | 'reauth.required' 已细化（见下）
 *   - 'handoff.start' | 'handoff.end' 已由 B8（issue #17）细化（见下）
 */

/** 会话状态机全部合法状态名（PRD line 286）。 */
export type ConversationState =
  'unauthenticated' | 'authenticated' | 'in_progress' | 'handed_off' | 'closed'

/** message.new payload：与 REST MessageOut 字段镜像（snake_case）。 */
export interface MessageNewPayload {
  id: number
  conversation_id: number
  source: 'user' | 'assistant' | 'agent' | 'system'
  content: string
  created_at: string // ISO 字符串（JSON 序列化后）
}

/** system.message payload：瞬时系统动作提示（不持久化为 Message）。 */
export interface SystemMessagePayload {
  content: string
  created_at: string // ISO 字符串
}

/** conversation.state payload：会话状态机流转通知（PRD line 286）。 */
export interface ConversationStatePayload {
  conversation_id: number
  old_state: ConversationState
  new_state: ConversationState
  changed_at: string // ISO 字符串
}

/** handoff.start payload：助理触发 Handoff（CONTEXT › 转接；B8 镜像后端 HandoffStartPayload）。 */
export interface HandoffStartPayload {
  conversation_id: number
  reason: string // 6 类触发原因（out_of_scope / transaction_failure / explicit_request / negative_sentiment / intent_loop / compliance_risk）
  offline_fallback: boolean // 离线兜底（已创建回呼请求 Ticket 派单到 Skill Group）
  ticket_id: number | null // 回呼请求 Ticket ID（offline_fallback 时非空）
  changed_at: string // ISO 字符串
}

/** handoff.end payload：坐席转回助理，Handoff 周期结束（B8 镜像后端 HandoffEndPayload）。 */
export interface HandoffEndPayload {
  conversation_id: number
  changed_at: string // ISO 字符串
}

/** ticket.update payload：工单状态变化通知（PRD line 282，B7 镜像后端 TicketUpdatePayload）。 */
export interface TicketUpdatePayload {
  id: number
  conversation_id: number
  ticket_type: 'transaction' | 'ticketing'
  status: string
  old_status: string
  changed_at: string // ISO 字符串
}

/** notification.push payload：站内通知（PRD line 282，B7 镜像后端 NotificationPushPayload）。 */
export interface NotificationPushPayload {
  id: number
  ticket_id: number
  message: string
  read: boolean
  created_at: string // ISO 字符串
}

/** agent.status payload：坐席状态变更通知（PRD line 282，B9 镜像后端 AgentStatusPayload）。 */
export interface AgentStatusPayload {
  agent_id: number
  status: 'online' | 'break' | 'offline' // 与 agent 前端 AgentStatus 三态一致
  changed_at: string // ISO 字符串
}

/** 四类办理类型名（US-8~US-11，镜像后端 TransactionTypeField）。 */
export type TransactionType = 'plan_change' | 'vadd_change' | 'suspend_hold' | 'recharge'

/** 结构化业务影响（二次确认 Modal 数据源，镜像后端 BusinessImpact）。 */
export interface BusinessImpactPayload {
  transaction_type: string
  summary: string
  plan_comparison: string // 套餐对比（当前 vs 目标）
  effective_time: string // 生效时间
  contract_impact: string // 合约影响
  fee_change: string // 费用变化
}

/** second.confirm payload：办理发起后请求二次确认（镜像后端 SecondConfirmPayload）。 */
export interface SecondConfirmPayload {
  conversation_id: number
  transaction_type: string
  business_impact: BusinessImpactPayload // snake_case 字段快照，前端直接消费
  requested_at: string // ISO 字符串
}

/** reauth.required payload：办理执行前服务密码复核请求（镜像后端 ReauthRequiredPayload）。 */
export interface ReauthRequiredPayload {
  ticket_id: number
  conversation_id: number
  message: string
  requested_at: string // ISO 字符串
}

export interface WsEventPayloadMap {
  'llm.token': Record<string, unknown>
  'message.new': MessageNewPayload
  'handoff.start': HandoffStartPayload
  'handoff.end': HandoffEndPayload
  'ticket.update': TicketUpdatePayload
  'notification.push': NotificationPushPayload
  'system.message': SystemMessagePayload
  'agent.status': AgentStatusPayload
  'conversation.state': ConversationStatePayload
  'second.confirm': SecondConfirmPayload
  'reauth.required': ReauthRequiredPayload
}

/** WS 事件 envelope。`event` 标识类型，`data` 携带对应 payload。 */
export interface WsEvent<E extends WsEventName = WsEventName> {
  event: E
  data: WsEventPayloadMap[E]
}

/** 类型守卫：判定任意值是否为合法 WS 事件名（运行时校验入站消息用）。 */
export function isWsEventName(value: unknown): value is WsEventName {
  return typeof value === 'string' && (WS_EVENT_NAMES as readonly string[]).includes(value)
}
