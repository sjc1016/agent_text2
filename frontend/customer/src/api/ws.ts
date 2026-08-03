/**
 * customer-web ChatWsClient（#24 UI-C-3）：accessToken WS 鉴权 + 断线自动重连。
 *
 * 后端契约（backend/app/ws/routes.py）：
 *   - 入口 `/ws`，JWT 查询参数 `?token=...`（access type）；未授权 → close 4401。
 *   - 服务端事件 envelope 统一 `{event, data}`，payload snake_case
 *     （与 frontend/shared/events.ts SSOT 镜像）。
 *   - 客户消息出站 `{type: 'message', conversation_id, content}`。
 * 部署契约（deploy/nginx.conf）：/ws 同源反代后端（无需 /api 前缀）。
 *
 * 职责边界（深模块：小接口，深实现）：
 *   - 只做传输：连接/鉴权/收发/断线重连，事件以 WsEvent 派发给 onEvent。
 *   - 不持有会话/消息状态（chat store 负责），断线语义经 onBrokenChange
 *     写入 ui store（顶栏「连接已断开，正在重连」条，PRD 状态策略错误行）。
 */

import { isWsEventName, type WsEvent } from 'shared/events'

export interface ChatWsOptions {
  /** 返回 accessToken（从 session store 读取；重连时重新取值）。 */
  getToken: () => string
  /** 收到合法 WS 事件（envelope 已解析、事件名已运行时校验）。 */
  onEvent: (event: WsEvent) => void
  /** 连接状态变化：true=断线，false=已连接（写入 ui.wsBroken）。 */
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

export class ChatWsClient {
  private readonly options: ChatWsOptions
  private ws: WebSocket | null = null
  private closedByUser = false
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null

  constructor(options: ChatWsOptions) {
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

  /**
   * 发送客户消息（出站契约 {type, conversation_id, content}）。
   * 返回是否已实际发送（WS 未连接时返回 false，供 chat store 标记发送失败/重发）。
   */
  sendMessage(conversationId: number, content: string): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false
    this.ws.send(JSON.stringify({ type: 'message', conversation_id: conversationId, content }))
    return true
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
