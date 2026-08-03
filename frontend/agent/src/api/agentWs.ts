/**
 * agent-console 坐席 WS 客户端（B9 契约，backend/app/ws/routes.py）。
 *
 * 后端契约：
 *   - 入口 `/ws`，JWT 查询参数 `?token=...`（type=agent_access）；未授权 → close 4401。
 *   - 坐席出站协议：`take_over`（接入会话）/ `message`（坐席消息）/
 *     `state_transition`（转回助理），payload snake_case。
 *   - 服务端事件 envelope 统一 `{event, data}`（与 frontend/shared/events.ts SSOT 镜像）。
 * 部署契约（deploy/nginx.conf）：/ws 同源反代后端（无需 /api 前缀）。
 *
 * 职责边界（同 customer-web ChatWsClient）：只做传输——连接/鉴权/收发/断线重连；
 * 事件以 WsEvent 派发给 onEvent，不持有会话/消息状态（ActiveChatView 负责）。
 */

import { isWsEventName, type WsEvent } from 'shared/events'

export interface AgentWsOptions {
  /** 返回坐席 accessToken（agent_access type；重连时重新取值）。 */
  getToken: () => string
  /** 收到合法 WS 事件（envelope 已解析、事件名已运行时校验）。 */
  onEvent: (event: WsEvent) => void
  /** WS 打开回调：坐席接入会话（sendTakeOver）时机。 */
  onOpen?: () => void
  /** 连接状态变化：true=断线，false=已连接。 */
  onBrokenChange?: (broken: boolean) => void
  /** 断线重连间隔 ms（默认 1000；测试注入小值）。 */
  reconnectDelayMs?: number
  /** 构建 WS URL（默认同源 /ws?token=...；测试可注入）。 */
  buildUrl?: (token: string) => string
}

/** 默认 URL：同源 /ws + JWT 查询参数（nginx 同源反代，无需 /api 前缀）。 */
function defaultBuildUrl(token: string): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws?token=${encodeURIComponent(token)}`
}

export class AgentWsClient {
  private readonly options: AgentWsOptions
  private ws: WebSocket | null = null
  private closedByUser = false
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null

  constructor(options: AgentWsOptions) {
    this.options = options
  }

  /** 打开连接（重连由内部调度；重复调用先关旧连接）。 */
  connect(): void {
    if (
      this.ws &&
      (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)
    ) {
      return
    }
    const buildUrl = this.options.buildUrl ?? defaultBuildUrl
    const ws = new WebSocket(buildUrl(this.options.getToken()))
    this.ws = ws

    ws.onopen = () => {
      this.options.onBrokenChange?.(false)
      this.options.onOpen?.()
    }
    ws.onmessage = (event: MessageEvent) => {
      this.handleMessage(event.data)
    }
    ws.onclose = () => {
      this.ws = null
      if (this.closedByUser) return
      this.options.onBrokenChange?.(true)
      this.scheduleReconnect()
    }
  }

  /** 接入会话（US-21）：绑定坐席到 handed_off 会话，成功后收 system.message 确认。 */
  sendTakeOver(conversationId: number): boolean {
    return this.send({ type: 'take_over', conversation_id: conversationId })
  }

  /** 发送坐席消息（出站契约 {type:'message', conversation_id, content}）。 */
  sendMessage(conversationId: number, content: string): boolean {
    return this.send({ type: 'message', conversation_id: conversationId, content })
  }

  /** 转回助理（US-26）：会话 handed_off → authenticated，agent_id 置空。 */
  sendStateTransition(conversationId: number): boolean {
    return this.send({ type: 'state_transition', conversation_id: conversationId })
  }

  /** 手动关闭：不再自动重连。 */
  close(): void {
    this.closedByUser = true
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }

  private send(payload: Record<string, unknown>): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false
    this.ws.send(JSON.stringify(payload))
    return true
  }

  private handleMessage(raw: unknown): void {
    let envelope: unknown
    try {
      envelope = typeof raw === 'string' ? JSON.parse(raw) : raw
    } catch {
      return
    }
    if (typeof envelope !== 'object' || envelope === null) return
    const { event, data } = envelope as { event?: unknown; data?: unknown }
    if (!isWsEventName(event)) return
    this.options.onEvent({ event, data } as WsEvent)
  }

  private scheduleReconnect(): void {
    if (this.closedByUser) return
    const delay = this.options.reconnectDelayMs ?? 1000
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }
}
