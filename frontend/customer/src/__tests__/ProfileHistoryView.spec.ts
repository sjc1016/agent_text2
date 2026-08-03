import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

import ProfileHistoryView from '../views/ProfileHistoryView.vue'
import { useSessionStore } from '../stores/session'

/**
 * #11 UI-C-5 循环 6：ProfileHistoryView（验收标准：点击会话历史进入只读视图）。
 *
 * 只读语义：展示会话消息历史（四类气泡），无输入区；返回按钮回 /profile。
 */

const fetchMock = vi.fn()

let router: Router

async function mountHistory(conversationId = 7) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSessionStore().setAuthenticated({ accessToken: 'at', refreshToken: 'rt' }, '13800001234')
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/profile/history/:id',
        component: ProfileHistoryView,
        props: true,
      },
      { path: '/profile', component: { template: '<div>profile</div>' } },
    ],
  })
  await router.push(`/profile/history/${conversationId}`)
  await router.isReady()
  const wrapper = mount(ProfileHistoryView, {
    global: { plugins: [router, pinia, ElementPlus] },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  localStorage.clear()
  fetchMock.mockReset()
  fetchMock.mockResolvedValue({
    ok: true,
    json: async () => [
      {
        id: 1,
        conversation_id: 7,
        source: 'user',
        content: '查一下话费余额',
        created_at: '2026-08-01T09:01:00Z',
      },
      {
        id: 2,
        conversation_id: 7,
        source: 'assistant',
        content: '您好，当前话费余额为 128.50 元',
        created_at: '2026-08-01T09:01:20Z',
      },
    ],
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ProfileHistoryView — readonly（验收标准：会话历史只读视图）', () => {
  it('渲染会话消息历史（消息气泡按来源渲染），无输入区', async () => {
    const wrapper = await mountHistory()

    // 标题 + 返回按钮
    expect(wrapper.find('[data-testid="history-back"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="history-title"]').text()).toContain('历史会话')

    // 消息历史：user/assistant 两类气泡内容可见
    const bubbles = wrapper.findAll('[data-testid="message-bubble"]')
    expect(bubbles).toHaveLength(2)
    expect(wrapper.text()).toContain('查一下话费余额')
    expect(wrapper.text()).toContain('您好，当前话费余额为 128.50 元')

    // 只读：无输入区 / 无发送按钮
    expect(wrapper.find('[data-testid="chat-textarea"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="chat-send"]').exists()).toBe(false)
  })

  it('点击返回按钮回 /profile', async () => {
    const wrapper = await mountHistory()

    await wrapper.find('[data-testid="history-back"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/profile')
  })
})
