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
 * TODO（后续切片）：
 *   - conversation 切片：细化 'llm.token' | 'message.new' | 'conversation.state' | 'system.message'
 *   - ticket 切片：细化 'ticket.update' | 'second.confirm' | 'reauth.required'
 *   - agent 切片：细化 'handoff.start' | 'handoff.end' | 'agent.status'
 *   - notification 切片：细化 'notification.push'
 */
export interface WsEventPayloadMap {
  'llm.token': Record<string, unknown>
  'message.new': Record<string, unknown>
  'handoff.start': Record<string, unknown>
  'handoff.end': Record<string, unknown>
  'ticket.update': Record<string, unknown>
  'notification.push': Record<string, unknown>
  'system.message': Record<string, unknown>
  'agent.status': Record<string, unknown>
  'conversation.state': Record<string, unknown>
  'second.confirm': Record<string, unknown>
  'reauth.required': Record<string, unknown>
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
