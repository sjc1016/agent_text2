import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ChatWsClient } from '../api/ws'
import type { WsEvent } from 'shared/events'

/**
 * #24 UI-C-3 循环：ChatWsClient（accessToken WS 鉴权 + 断线重连）。
 *
 * 后端契约（backend/app/ws/routes.py）：
 *   WS 入口 /ws，JWT 查询参数 `?token=...`（access type），未授权 → close 4401。
 *   accept 后 envelope 统一 {event, data}；客户消息入站格式 {type:'message', conversation_id, content}。
 * 部署契约（deploy/nginx.conf）：/ws 同源反代后端，无需 /api 前缀。
 */

/** jsdom 不实现 WebSocket：测试用 Mock 记录 URL/send，并手动触发 open/message/close。 */
class MockWebSocket {
  static instances: MockWebSocket[] = []
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3

  url: string
  readyState = MockWebSocket.CONNECTING
  sent: string[] = []
  onopen: ((event: unknown) => void) | null = null
  onmessage: ((event: { data: unknown }) => void) | null = null
  onclose: ((event: { code?: number }) => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close(code?: number) {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.({ code })
  }
}

/** 模拟服务端 accept 最近一次连接，返回该实例供后续 push。 */
function acceptLast(): MockWebSocket {
  const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
  ws.readyState = MockWebSocket.OPEN
  ws.onopen?.({})
  return ws
}

/** 模拟服务端推送 {event, data} envelope。 */
function pushTo(ws: MockWebSocket, envelope: unknown) {
  ws.onmessage?.({ data: JSON.stringify(envelope) })
}

const received: WsEvent[] = []
const brokenStates: boolean[] = []

beforeEach(() => {
  MockWebSocket.instances = []
  received.length = 0
  brokenStates.length = 0
  vi.useFakeTimers()
  vi.stubGlobal('WebSocket', MockWebSocket)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

function makeClient(reconnectDelayMs = 10): ChatWsClient {
  return new ChatWsClient({
    getToken: () => 'at',
    onEvent: (event) => received.push(event),
    onBrokenChange: (broken) => brokenStates.push(broken),
    reconnectDelayMs,
  })
}

describe('ChatWsClient — WS 鉴权与事件收发（#24）', () => {
  it('connect 打开 /ws?token=accessToken（JWT 查询参数鉴权）', () => {
    makeClient().connect()

    expect(MockWebSocket.instances).toHaveLength(1)
    const url = new URL(MockWebSocket.instances[0].url, 'http://localhost')
    expect(url.pathname).toBe('/ws')
    expect(url.searchParams.get('token')).toBe('at')
  })

  it('收到合法 envelope 解析并按事件名派发（envelope {event, data}）', () => {
    const client = makeClient()
    client.connect()
    const ws = acceptLast()

    pushTo(ws, { event: 'system.message', data: { content: '会话已建立', created_at: 't' } })

    expect(received).toHaveLength(1)
    expect(received[0].event).toBe('system.message')
    expect(received[0].data).toEqual({ content: '会话已建立', created_at: 't' })
  })

  it('未知事件名被忽略（isWsEventName 运行时校验）', () => {
    const client = makeClient()
    client.connect()
    const ws = acceptLast()

    pushTo(ws, { event: 'bogus.event', data: {} })

    expect(received).toHaveLength(0)
  })

  it('sendMessage 以 {type, conversation_id, content} 出站', () => {
    const client = makeClient()
    client.connect()
    const ws = acceptLast()

    client.sendMessage(7, '查话费')

    expect(ws.sent).toHaveLength(1)
    expect(JSON.parse(ws.sent[0])).toEqual({
      type: 'message',
      conversation_id: 7,
      content: '查话费',
    })
  })

  it('意外断线 → broken=true + 自动重连 → 重连成功 broken=false', () => {
    const client = makeClient(50)
    client.connect()
    acceptLast()

    MockWebSocket.instances[0].close(1006) // 异常关闭

    expect(brokenStates[brokenStates.length - 1]).toBe(true)

    vi.advanceTimersByTime(50)
    expect(MockWebSocket.instances).toHaveLength(2)
    acceptLast()
    expect(brokenStates[brokenStates.length - 1]).toBe(false)
  })

  it('close() 手动关闭后不再重连', () => {
    const client = makeClient(50)
    client.connect()
    acceptLast()

    client.close()
    vi.advanceTimersByTime(500)

    expect(MockWebSocket.instances).toHaveLength(1)
    expect(brokenStates).not.toContain(true)
  })

  it('未授权 close 4401 同样进入重连（PRD 错误态「正在重连」）', () => {
    const client = makeClient(50)
    client.connect()
    acceptLast()

    MockWebSocket.instances[0].close(4401)

    expect(brokenStates[brokenStates.length - 1]).toBe(true)
    vi.advanceTimersByTime(50)
    expect(MockWebSocket.instances).toHaveLength(2)
  })
})
