import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

import ProfileView from '../views/ProfileView.vue'
import ProfileHistoryView from '../views/ProfileHistoryView.vue'
import { useSessionStore } from '../stores/session'
import { useChatStore } from '../stores/chat'
import type { CustomerProfile } from '../api/customers'
import type { Conversation } from '../api/conversations'

/**
 * #11 UI-C-5 循环：ProfileView（States 矩阵逐行验证）。
 *
 * 行序循环：default → visitor-empty → history-empty → loading → logout → 只读视图。
 * 测行为不测像素：验证 data-testid 结构 + 可观察行为（账号卡片/历史列表/徽章/导航/退出）。
 */

const fetchMock = vi.fn()

let router: Router

/** 会话历史 fixture（镜像 backend ConversationOut + MessageOut）。 */
interface ConversationFixture extends Conversation {
  messages: Array<{
    id: number
    source: string
    content: string
    created_at: string
  }>
}

/** 挂载 ProfileView；setup 在组件挂载前于同一 pinia 上注入状态。 */
async function mountProfile(setup?: () => void) {
  const pinia = createPinia()
  setActivePinia(pinia)
  setup?.()
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/profile', component: ProfileView },
      { path: '/profile/history/:id', component: ProfileHistoryView },
      { path: '/auth', component: { template: '<div>auth</div>' } },
    ],
  })
  await router.push('/profile')
  await router.isReady()
  const wrapper = mount(ProfileView, {
    global: { plugins: [router, pinia, ElementPlus] },
  })
  await flushPromises()
  return wrapper
}

/** 已认证：写入 JWT + 号码脱敏（session store 的 setAuthenticated 同 /auth 成功路径）。 */
function setAuthenticated() {
  useSessionStore().setAuthenticated({ accessToken: 'at', refreshToken: 'rt' }, '13800001234')
}

/** 账户资料 fixture（镜像 backend CustomerProfileOut；B13 真实数据源）。 */
const profileFixture: CustomerProfile = {
  id: 9,
  phone: '13800001234',
  name: '张三',
  balance: 88.5,
  plan_name: '畅享套餐',
  contract_expiry_date: '2027-12-31',
}

/**
 * 按 URL 路由 fetch mock：/api/customers/me 账户资料 +
 * /api/conversations 列表 + /api/conversations/{id}/messages 历史。
 */
function mockConversationData(
  conversations: ConversationFixture[],
  profile: CustomerProfile = profileFixture,
) {
  fetchMock.mockImplementation((url: string) => {
    if (url === '/api/customers/me') {
      return Promise.resolve({ ok: true, json: async () => profile })
    }
    if (url === '/api/conversations') {
      return Promise.resolve({
        ok: true,
        json: async () =>
          conversations.map((c) => ({
            id: c.id,
            customer_id: c.customer_id,
            status: c.status,
            created_at: c.created_at,
          })),
      })
    }
    const match = url.match(/^\/api\/conversations\/(\d+)\/messages$/)
    if (match) {
      const conv = conversations.find((c) => c.id === Number(match[1]))
      return Promise.resolve({ ok: true, json: async () => conv?.messages ?? [] })
    }
    return Promise.resolve({ ok: false, json: async () => ({ detail: 'not found' }) })
  })
}

beforeEach(() => {
  localStorage.clear()
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ProfileView — default（States 矩阵 default）', () => {
  it('渲染账号卡片（头像首字母 + 号码脱敏 + 已认证徽章 + 套餐简述）+ 会话历史列表（起止时间 + 末条预览 + Closed 徽章）+ 退出按钮', async () => {
    const wrapper = await mountProfile(() => {
      setAuthenticated()
      mockConversationData([
        {
          id: 1,
          customer_id: 9,
          status: 'closed',
          created_at: '2026-08-01T09:00:00Z',
          messages: [
            {
              id: 11,
              source: 'user',
              content: '查一下话费余额',
              created_at: '2026-08-01T09:01:00Z',
            },
            {
              id: 12,
              source: 'assistant',
              content: '您好，当前话费余额为 128.50 元',
              created_at: '2026-08-01T09:01:20Z',
            },
          ],
        },
      ])
    })

    // 账号卡片：头像首字母 + 号码脱敏 + 已认证 Primary 徽章 + 套餐简述
    const card = wrapper.find('[data-testid="account-card"]')
    expect(card.exists()).toBe(true)
    expect(card.find('[data-testid="account-avatar"]').text()).toContain('1')
    expect(card.text()).toContain('138****1234')
    expect(card.find('[data-testid="account-status-badge"]').text()).toContain('已认证')
    expect(card.text()).toContain('畅享套餐')

    // 会话历史区块标题 + 列表行（起止时间 + 末条消息预览 + Closed→Neutral 徽章）
    expect(wrapper.find('[data-testid="history-title"]').text()).toContain('会话历史')
    const rows = wrapper.findAll('[data-testid="history-row"]')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('2026-08-01')
    expect(rows[0].text()).toContain('您好，当前话费余额为 128.50 元')
    const badge = rows[0].find('[data-testid="history-status-badge"]')
    expect(badge.text()).toContain('已结束')
    expect(badge.attributes('data-variant')).toBe('neutral')

    // 底部退出登录反色按钮
    const logout = wrapper.find('[data-testid="logout-button"]')
    expect(logout.exists()).toBe(true)
    expect(logout.text()).toContain('退出登录')
  })
})

describe('ProfileView — visitor-empty（States 矩阵 visitor-empty）', () => {
  it('访客显示「访客身份」+ 主按钮「去认证」，不请求数据', async () => {
    const wrapper = await mountProfile()
    // 未认证：不请求会话历史
    expect(fetchMock).not.toHaveBeenCalled()

    const card = wrapper.find('[data-testid="account-card"]')
    expect(card.exists()).toBe(true)
    expect(card.text()).toContain('访客身份')

    const goAuth = card.find('[data-testid="go-auth-button"]')
    expect(goAuth.exists()).toBe(true)
    expect(goAuth.text()).toContain('去认证')
  })

  it('点击「去认证」跳转 /auth', async () => {
    const wrapper = await mountProfile()

    await wrapper.find('[data-testid="go-auth-button"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/auth')
  })
})

describe('ProfileView — history-empty（States 矩阵 history-empty）', () => {
  it('无会话历史显示空状态（居中插画 + 主文案「暂无历史会话」），不渲染列表', async () => {
    const wrapper = await mountProfile(() => {
      setAuthenticated()
      mockConversationData([])
    })

    expect(wrapper.find('[data-testid="history-list"]').exists()).toBe(false)
    const empty = wrapper.find('[data-testid="history-empty"]')
    expect(empty.exists()).toBe(true)
    expect(empty.find('[data-testid="history-empty-illustration"]').exists()).toBe(true)
    expect(empty.text()).toContain('暂无历史会话')
  })
})

describe('ProfileView — loading（States 矩阵 loading：骨架屏）', () => {
  it('加载中显示骨架屏（48px 行左头像圆形 + 右两行文本条），加载完成切换列表/空态', async () => {
    let resolveList!: (value: unknown) => void
    const pending = new Promise((resolve) => {
      resolveList = resolve
    })

    const wrapper = await mountProfile(() => {
      setAuthenticated()
      fetchMock.mockImplementation((url: string) => {
        if (url === '/api/conversations') return pending
        if (url === '/api/customers/me') {
          return Promise.resolve({ ok: true, json: async () => profileFixture })
        }
        return Promise.resolve({ ok: true, json: async () => [] })
      })
    })

    // 加载中：骨架屏（aria-busy），列表/空态不渲染
    const skeleton = wrapper.find('[data-testid="history-skeleton"]')
    expect(skeleton.exists()).toBe(true)
    expect(skeleton.attributes('aria-busy')).toBe('true')
    expect(skeleton.findAll('[data-testid="history-skeleton-item"]').length).toBeGreaterThan(0)
    expect(wrapper.find('[data-testid="history-list"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="history-empty"]').exists()).toBe(false)

    // 加载完成：骨架屏消失，空态渲染
    resolveList({ ok: true, json: async () => [] })
    await flushPromises()
    expect(wrapper.find('[data-testid="history-skeleton"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="history-empty"]').exists()).toBe(true)
  })
})

describe('ProfileView — logout（验收标准：退出登录清除会话并返回访客态）', () => {
  it('点击退出登录清除认证与会话数据，账号卡片回访客态', async () => {
    const wrapper = await mountProfile(() => {
      setAuthenticated()
      mockConversationData([
        {
          id: 1,
          customer_id: 9,
          status: 'closed',
          created_at: '2026-08-01T09:00:00Z',
          messages: [
            {
              id: 11,
              source: 'user',
              content: '查一下话费余额',
              created_at: '2026-08-01T09:01:00Z',
            },
          ],
        },
      ])
      // 预置旧对话流数据，验证退出时一并清除（US-17「清除会话」）
      const chat = useChatStore()
      chat.conversationId = 1
      chat.messages = [
        {
          id: 1,
          conversation_id: 1,
          source: 'user',
          content: '查一下话费余额',
          created_at: '2026-08-01T09:01:00Z',
        },
      ]
    })

    expect(wrapper.find('[data-testid="account-card"]').text()).toContain('138****1234')

    await wrapper.find('[data-testid="logout-button"]').trigger('click')
    await flushPromises()

    // session 凭证与持久化清除，状态回访客
    const session = useSessionStore()
    expect(session.accessToken).toBe('')
    expect(session.maskedPhone).toBe('')
    expect(session.isAuthenticated).toBe(false)
    expect(localStorage.getItem('customer.auth')).toBeNull()

    // chat store 对话流一并清除
    const chat = useChatStore()
    expect(chat.conversationId).toBeNull()
    expect(chat.messages).toHaveLength(0)

    // UI 回访客态：账号卡片显示「访客身份」+「去认证」
    const card = wrapper.find('[data-testid="account-card"]')
    expect(card.text()).toContain('访客身份')
    expect(card.find('[data-testid="go-auth-button"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="logout-button"]').exists()).toBe(false)
  })
})

describe('ProfileView — history-readonly（验收标准：点击会话历史进入只读视图）', () => {
  it('点击会话历史行跳转 /profile/history/{id}', async () => {
    const wrapper = await mountProfile(() => {
      setAuthenticated()
      mockConversationData([
        {
          id: 7,
          customer_id: 9,
          status: 'closed',
          created_at: '2026-08-01T09:00:00Z',
          messages: [
            {
              id: 11,
              source: 'user',
              content: '查一下话费余额',
              created_at: '2026-08-01T09:01:00Z',
            },
          ],
        },
      ])
    })

    await wrapper.find('[data-testid="history-row"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/profile/history/7')
  })
})
