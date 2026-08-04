import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useChatStore } from '../stores/chat'
import { useSessionStore } from '../stores/session'
import { useUiStore } from '../stores/ui'
import type { WsEvent } from 'shared/events'

/**
 * #24 UI-C-3 循环：chat store（ensureConversation / sendMessage / WS 事件消费）。
 *
 * 后端契约（B1-B9 已合并）：
 *   POST /api/conversations（Bearer）→ 会话（#24 对话页入口）
 *   WS /ws?token=...：envelope {event, data}；customer 消息出站 {type:'message', conversation_id, content}
 *   WS accept 后首事件 system.message「会话已建立，请问有什么可以帮您？」
 *     （backend _SESSION_OPENED_CONTENT）——新会话空状态由前端渲染问候气泡，store 吞掉该瞬时提示。
 */

// vi.mock 工厂可引用 mock* 前缀变量（vitest hoisting 规则）。
const sendMessageMock = vi.fn()
const connectMock = vi.fn()
const closeMock = vi.fn()
let capturedOptions: {
  getToken: () => string
  onEvent: (event: WsEvent) => void
  onBrokenChange: (broken: boolean) => void
}

vi.mock('../api/ws', () => ({
  ChatWsClient: class {
    constructor(options: typeof capturedOptions) {
      capturedOptions = options
    }
    connect() {
      connectMock()
    }
    sendMessage(...args: unknown[]) {
      return sendMessageMock(...args)
    }
    close() {
      closeMock()
    }
  },
}))

const fetchMock = vi.fn()

function pushWs(event: WsEvent) {
  capturedOptions.onEvent(event)
}

function makeAuthenticated() {
  const session = useSessionStore()
  session.setAuthenticated({ accessToken: 'at', refreshToken: 'rt' }, '13800001234')
  return session
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  fetchMock.mockReset()
  fetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({
      id: 7,
      customer_id: 9,
      status: 'authenticated',
      created_at: '2026-08-03T00:00:00Z',
    }),
  })
  vi.stubGlobal('fetch', fetchMock)
  sendMessageMock.mockReset()
  connectMock.mockReset()
  closeMock.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ensureConversation / init（#24）', () => {
  it('未认证：不创建会话不连 WS（访客空状态由视图处理）', async () => {
    const store = useChatStore()
    await store.init()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(store.conversationId).toBeNull()
    expect(connectMock).not.toHaveBeenCalled()
  })

  it('已认证：POST /api/conversations 创建会话并连 WS', async () => {
    makeAuthenticated()
    const store = useChatStore()
    await store.init()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/conversations')
    expect(init.method).toBe('POST')
    expect(store.conversationId).toBe(7)
    expect(connectMock).toHaveBeenCalledTimes(1)
  })

  it('已持有会话时不重复创建', async () => {
    makeAuthenticated()
    const store = useChatStore()
    store.conversationId = 3
    await store.init()

    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('sendMessage / retrySend（#24）', () => {
  it('发送成功：出站 {type, conversation_id, content}，无失败内容', async () => {
    makeAuthenticated()
    const store = useChatStore()
    await store.init()
    sendMessageMock.mockReturnValue(true)

    store.sendMessage('查话费')

    expect(sendMessageMock).toHaveBeenCalledWith(7, '查话费')
    expect(store.failedContent).toBeNull()
  })

  it('发送失败（WS 未连接）：记录 failedContent 供错误态重发', async () => {
    makeAuthenticated()
    const store = useChatStore()
    await store.init()
    sendMessageMock.mockReturnValue(false)

    store.sendMessage('查话费')

    expect(store.failedContent).toBe('查话费')
    expect(store.showGreeting).toBe(false)
  })

  it('retrySend 重发成功清除 failedContent', async () => {
    makeAuthenticated()
    const store = useChatStore()
    await store.init()
    sendMessageMock.mockReturnValue(false)
    store.sendMessage('查话费')
    expect(store.failedContent).toBe('查话费')

    sendMessageMock.mockReturnValue(true)
    store.retrySend()

    expect(sendMessageMock).toHaveBeenCalledWith(7, '查话费')
    expect(store.failedContent).toBeNull()
  })
})

describe('WS 事件消费（#24）', () => {
  it('llm.token：置助理生成中并逐 token 累积（信号脉冲 → 文本）', async () => {
    makeAuthenticated()
    const store = useChatStore()
    await store.init()

    pushWs({ event: 'llm.token', data: { conversation_id: 7, token: '您' } })
    pushWs({ event: 'llm.token', data: { conversation_id: 7, token: '好' } })

    expect(store.assistantPending).toBe(true)
    expect(store.assistantPartial).toBe('您好')
  })

  it('message.new(assistant)：入对话流并结束生成态', async () => {
    makeAuthenticated()
    const store = useChatStore()
    await store.init()
    pushWs({ event: 'llm.token', data: { conversation_id: 7, token: 'x' } })

    pushWs({
      event: 'message.new',
      data: { id: 2, conversation_id: 7, source: 'assistant', content: '您好', created_at: 't' },
    })

    expect(store.messages).toHaveLength(1)
    expect(store.messages[0].source).toBe('assistant')
    expect(store.assistantPending).toBe(false)
    expect(store.assistantPartial).toBe('')
    expect(store.showGreeting).toBe(false)
  })

  it('message.new(user)：入对话流并清除 failedContent（已送达）', async () => {
    makeAuthenticated()
    const store = useChatStore()
    await store.init()
    sendMessageMock.mockReturnValue(false)
    store.sendMessage('查话费')
    expect(store.failedContent).toBe('查话费')

    pushWs({
      event: 'message.new',
      data: { id: 1, conversation_id: 7, source: 'user', content: '查话费', created_at: 't' },
    })

    expect(store.failedContent).toBeNull()
    expect(store.messages[0].source).toBe('user')
  })

  it('system.message：吞掉「会话已建立」瞬时提示，其余作为系统消息入流', async () => {
    makeAuthenticated()
    const store = useChatStore()
    await store.init()

    pushWs({
      event: 'system.message',
      data: { content: '会话已建立，请问有什么可以帮您？', created_at: 't' },
    })
    expect(store.messages).toHaveLength(0)

    pushWs({
      event: 'system.message',
      data: { content: '正在为您转接人工坐席，请稍候', created_at: 't' },
    })
    expect(store.messages).toHaveLength(1)
    expect(store.messages[0].source).toBe('system')
    expect(store.messages[0].content).toBe('正在为您转接人工坐席，请稍候')
  })

  it('conversation.state：写入 session store 驱动顶栏徽章', async () => {
    makeAuthenticated()
    const store = useChatStore()
    await store.init()

    pushWs({
      event: 'conversation.state',
      data: {
        conversation_id: 7,
        old_state: 'authenticated',
        new_state: 'in_progress',
        changed_at: 't',
      },
    })
    expect(useSessionStore().conversationState).toBe('in_progress')

    pushWs({
      event: 'conversation.state',
      data: {
        conversation_id: 7,
        old_state: 'in_progress',
        new_state: 'handed_off',
        changed_at: 't',
      },
    })
    expect(store.isHandedOff).toBe(true)
  })

  it('second.confirm：置二次确认 Modal 数据', async () => {
    makeAuthenticated()
    const store = useChatStore()
    await store.init()

    pushWs({
      event: 'second.confirm',
      data: {
        conversation_id: 7,
        transaction_type: 'recharge',
        business_impact: {
          transaction_type: 'recharge',
          summary: '充值 100 元',
          plan_comparison: '-',
          effective_time: '立即生效',
          contract_impact: '无',
          fee_change: '支出 100 元',
        },
        requested_at: 't',
      },
    })

    expect(store.pendingConfirm?.transaction_type).toBe('recharge')
    expect(store.pendingConfirm?.business_impact.fee_change).toBe('支出 100 元')
  })

  it('reauth.required：置服务密码复核 Modal 数据', async () => {
    makeAuthenticated()
    const store = useChatStore()
    await store.init()

    pushWs({
      event: 'reauth.required',
      data: { ticket_id: 5, conversation_id: 7, message: '请再次输入服务密码', requested_at: 't' },
    })

    expect(store.pendingReauth?.ticket_id).toBe(5)
  })
})

describe('空状态问候（#24）', () => {
  it('showGreeting：新会话（无消息）为 true，有消息后为 false', async () => {
    makeAuthenticated()
    const store = useChatStore()
    await store.init()

    expect(store.showGreeting).toBe(true)

    pushWs({
      event: 'message.new',
      data: { id: 1, conversation_id: 7, source: 'user', content: 'hi', created_at: 't' },
    })
    expect(store.showGreeting).toBe(false)
  })
})

describe('issue #65：会话未创建 / 凭证过期', () => {
  it('sendMessage 在 conversationId 为 null 时给出错误态提示（不再静默吞掉）', async () => {
    makeAuthenticated()
    const store = useChatStore()
    // 不 init：会话未创建（如建会话失败）
    store.sendMessage('查话费')

    expect(store.failedContent).toBe('查话费')
    expect(store.showGreeting).toBe(false)
    expect(sendMessageMock).not.toHaveBeenCalled()
  })

  it('retrySend 在会话未创建时先建会话再发送（重发不丢消息）', async () => {
    makeAuthenticated()
    const store = useChatStore()
    store.sendMessage('查话费')
    expect(store.failedContent).toBe('查话费')

    sendMessageMock.mockReturnValue(true)
    await store.retrySend()

    expect(fetchMock).toHaveBeenCalledWith('/api/conversations', expect.anything())
    expect(sendMessageMock).toHaveBeenCalledWith(7, '查话费')
    expect(store.failedContent).toBeNull()
  })

  it('建会话 401（access 过期，带 WWW-Authenticate）→ 自动刷新后重试建会话成功', async () => {
    makeAuthenticated()
    fetchMock
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: { get: () => 'Bearer' },
        json: async () => ({ detail: '未认证' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ access_token: 'fresh' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: 7,
          customer_id: 9,
          status: 'authenticated',
          created_at: '2026-08-03T00:00:00Z',
        }),
      })

    const store = useChatStore()
    await store.init()

    expect(store.conversationId).toBe(7)
    expect(useSessionStore().accessToken).toBe('fresh')
    expect(connectMock).toHaveBeenCalledTimes(1)
  })

  it('logout：关闭 WS（停止重连）+ 清空对话流 + 断线条复位', async () => {
    makeAuthenticated()
    const store = useChatStore()
    await store.init()
    useUiStore().setWsBroken(true)

    store.logout()

    // 关闭 WS（含上一测试遗留 client 在 connectWs 时被关，故至少一次）
    expect(closeMock).toHaveBeenCalled()
    expect(store.conversationId).toBeNull()
    expect(store.messages).toHaveLength(0)
    expect(useUiStore().wsBroken).toBe(false)
  })
})
