import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import ElementPlus from 'element-plus'

import ChatView from '../views/ChatView.vue'
import { useChatStore } from '../stores/chat'
import { useSessionStore } from '../stores/session'
import type { ChatMessage } from '../api/conversations'

/**
 * #24 UI-C-3 循环：ChatView（States 矩阵逐行验证）。
 *
 * 行序循环：default → empty → loading → error → disabled → handoff-waiting
 *   （二次确认/复核 Modal 单独 spec：ChatViewModals.spec.ts）
 * 测行为不测像素：验证 data-testid 结构 + 可观察行为（发送/换行/重发/禁用/导航）。
 */

// vi.mock 工厂可引用 mock* 前缀变量。
const sendMessageMock = vi.fn()
vi.mock('../api/ws', () => ({
  ChatWsClient: class {
    connect() {}
    sendMessage(...args: unknown[]) {
      return sendMessageMock(...args)
    }
    close() {}
  },
}))

const fetchMock = vi.fn()

let router: Router

/**
 * 挂载 ChatView。setup 在组件挂载前于同一 pinia 上注入状态
 * （组件 onMounted 的 chat.init() 依赖该 pinia）。
 */
async function mountChat(setup?: () => void) {
  const pinia: Pinia = createPinia()
  setActivePinia(pinia)
  setup?.()
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/chat', component: ChatView },
      { path: '/auth', component: { template: '<div>auth</div>' } },
    ],
  })
  await router.push('/chat')
  await router.isReady()
  const wrapper = mount(ChatView, {
    global: { plugins: [router, pinia, ElementPlus] },
  })
  await flushPromises()
  return wrapper
}

/** 已认证 + 会话就绪（conversationId=7，消息列表可注入）。 */
function makeAuthConversation(messages: ChatMessage[] = []) {
  useSessionStore().setAuthenticated({ accessToken: 'at', refreshToken: 'rt' }, '13800001234')
  const chat = useChatStore()
  chat.conversationId = 7
  chat.messages.push(...messages)
  return chat
}

function msg(id: number, source: ChatMessage['source'], content: string): ChatMessage {
  return { id, conversation_id: 7, source, content, created_at: 't' }
}

beforeEach(() => {
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
  sendMessageMock.mockReturnValue(true)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ChatView — default（States 矩阵 default）', () => {
  it('渲染对话流区 + 输入区（textarea + 发送按钮）', async () => {
    const wrapper = await mountChat(() => makeAuthConversation())

    expect(wrapper.find('[data-testid="chat-messages"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="chat-textarea"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="chat-send"]').exists()).toBe(true)
  })

  it('四类气泡渲染（user/assistant/agent/system 各带 source 标识）', async () => {
    const wrapper = await mountChat(() =>
      makeAuthConversation([
        msg(1, 'assistant', '您好，请问需要什么帮助？'),
        msg(2, 'user', '查一下话费'),
        msg(3, 'agent', '我是坐席小王'),
        msg(4, 'system', '会话已转接给坐席'),
      ]),
    )

    const bubbles = wrapper.findAll('[data-testid="message-bubble"]')
    expect(bubbles).toHaveLength(4)
    const sources = bubbles.map((b) => b.attributes('data-source'))
    expect(sources).toEqual(['assistant', 'user', 'agent', 'system'])
    expect(bubbles[0].text()).toContain('您好，请问需要什么帮助？')
  })

  it('回车发送：调用 store.sendMessage 并清空输入框', async () => {
    const wrapper = await mountChat(() => makeAuthConversation())
    const textarea = wrapper.find('[data-testid="chat-textarea"]')

    await textarea.setValue('查话费')
    await textarea.trigger('keydown.enter')

    expect(sendMessageMock).toHaveBeenCalledWith(7, '查话费')
    expect((textarea.element as HTMLTextAreaElement).value).toBe('')
  })

  it('Shift+回车换行：不发送且保留输入', async () => {
    const wrapper = await mountChat(() => makeAuthConversation())
    const textarea = wrapper.find('[data-testid="chat-textarea"]')

    await textarea.setValue('第一行\n')
    await textarea.trigger('keydown.enter', { shiftKey: true })

    expect(sendMessageMock).not.toHaveBeenCalled()
    expect((textarea.element as HTMLTextAreaElement).value).toBe('第一行\n')
  })

  it('输入为空时发送按钮禁用', async () => {
    const wrapper = await mountChat(() => makeAuthConversation())
    const send = wrapper.find('[data-testid="chat-send"]')

    expect((send.element as HTMLButtonElement).disabled).toBe(true)

    await wrapper.find('[data-testid="chat-textarea"]').setValue('有内容')
    expect((wrapper.find('[data-testid="chat-send"]').element as HTMLButtonElement).disabled).toBe(
      false,
    )
  })
})

describe('ChatView — empty（States 矩阵 empty）', () => {
  it('新会话（无消息）助理先发问候气泡', async () => {
    const wrapper = await mountChat(() => makeAuthConversation())

    const greeting = wrapper.find('[data-testid="greeting-bubble"]')
    expect(greeting.exists()).toBe(true)
    expect(greeting.text()).toContain('您好，我是电信客服助理，请问有什么可以帮您？')
  })

  it('有消息后问候气泡消失', async () => {
    const wrapper = await mountChat(() => makeAuthConversation([msg(1, 'user', 'hi')]))

    expect(wrapper.find('[data-testid="greeting-bubble"]').exists()).toBe(false)
  })
})

describe('ChatView — loading（States 矩阵 loading）', () => {
  it('助理生成中：信号脉冲 3 圆点 + 累积文本', async () => {
    const wrapper = await mountChat(() => {
      const chat = makeAuthConversation()
      chat.assistantPending = true
      chat.assistantPartial = '正在为您查'
    })

    const loading = wrapper.find('[data-testid="assistant-loading"]')
    expect(loading.exists()).toBe(true)
    expect(loading.findAll('.signal-pulse__dot')).toHaveLength(3)
    expect(loading.text()).toContain('正在为您查')
  })
})

describe('ChatView — error（States 矩阵 error）', () => {
  it('发送失败：用户气泡 + Error 图标 + 重发按钮；点击重发调 sendMessage', async () => {
    const wrapper = await mountChat(() => {
      const chat = makeAuthConversation()
      chat.failedContent = '查话费'
    })

    const failed = wrapper.find('[data-testid="failed-bubble"]')
    expect(failed.exists()).toBe(true)
    expect(failed.find('[data-testid="failed-error-icon"]').exists()).toBe(true)
    expect(failed.text()).toContain('查话费')

    const retry = wrapper.find('[data-testid="retry-button"]')
    expect(retry.text()).toContain('重发')
    await retry.trigger('click')

    expect(sendMessageMock).toHaveBeenCalledWith(7, '查话费')
  })
})

describe('ChatView — disabled（States 矩阵 disabled）', () => {
  it('Handed-off 等待坐席：输入框禁用 + placeholder「正在为您转接坐席…」', async () => {
    const wrapper = await mountChat(() => {
      makeAuthConversation()
      useSessionStore().conversationState = 'handed_off'
    })

    const textarea = wrapper.find('[data-testid="chat-textarea"]')
    expect((textarea.element as HTMLTextAreaElement).disabled).toBe(true)
    expect(textarea.attributes('placeholder')).toBe('正在为您转接坐席…')
    expect((wrapper.find('[data-testid="chat-send"]').element as HTMLButtonElement).disabled).toBe(
      true,
    )
  })

  it('访客（未认证）：输入禁用 + 去认证按钮跳转 /auth', async () => {
    const wrapper = await mountChat()

    const textarea = wrapper.find('[data-testid="chat-textarea"]')
    expect((textarea.element as HTMLTextAreaElement).disabled).toBe(true)

    const goAuth = wrapper.find('[data-testid="go-auth-button"]')
    expect(goAuth.exists()).toBe(true)
    await goAuth.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/auth')
  })
})

describe('ChatView — handoff-waiting（States 矩阵 handoff-waiting）', () => {
  it('转接中：系统转接消息 + 信号脉冲（等待坐席接入）', async () => {
    const wrapper = await mountChat(() => {
      makeAuthConversation([
        msg(1, 'user', '转人工'),
        msg(-1, 'system', '正在为您转接人工坐席，请稍候'),
      ])
      useSessionStore().conversationState = 'handed_off'
    })

    const systemBubble = wrapper.find('[data-testid="message-bubble"][data-source="system"]')
    expect(systemBubble.exists()).toBe(true)
    expect(systemBubble.text()).toContain('正在为您转接人工坐席，请稍候')

    expect(wrapper.find('[data-testid="handoff-pulse"]').exists()).toBe(true)
    expect(
      wrapper.find('[data-testid="handoff-pulse"]').findAll('.signal-pulse__dot'),
    ).toHaveLength(3)
  })
})

describe('ChatView — 登出自动跳转（issue #65）', () => {
  it('登出（refresh 失败自动登出）：停 WS + 清对话流 + 自动跳转 /auth', async () => {
    await mountChat(() => makeAuthConversation())

    // 模拟 http 层 refresh 失败自动 logout（access/refresh 全部失效）
    useSessionStore().logout()
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/auth')

    const chat = useChatStore()
    expect(chat.conversationId).toBeNull()
    expect(chat.messages).toHaveLength(0)
  })
})
