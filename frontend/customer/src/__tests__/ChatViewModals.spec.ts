import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import ElementPlus from 'element-plus'

import ChatView from '../views/ChatView.vue'
import { useChatStore } from '../stores/chat'
import { useSessionStore } from '../stores/session'
import type { ReauthRequiredPayload, SecondConfirmPayload } from 'shared/events'

/**
 * #24 UI-C-3 循环：ChatView 两类 Modal（States 矩阵
 * second-confirm-modal / reauth-modal）。
 *
 * 后端契约（B1/B6 已合并）：
 *   POST /api/transactions/confirm（Bearer access）→ 201 TicketOut（二次确认入队）
 *   POST /api/auth/reauth（Bearer access）→ {execute_token}（服务密码复核）
 *   POST /api/transactions/{ticket_id}/execute（Bearer execute_token）→ 200 TicketOut
 * 测行为不测像素：验证 Modal 结构 + REST 调用链 + 成功关闭/失败 inline 错误。
 */

// vi.mock 工厂可引用 mock* 前缀变量。
vi.mock('../api/ws', () => ({
  ChatWsClient: class {
    connect() {}
    sendMessage() {
      return true
    }
    close() {}
  },
}))

const fetchMock = vi.fn()

/** 默认 fetch 路由：创建会话 + 成功路径可覆盖。 */
function defaultFetch(url: string) {
  if (url === '/api/conversations') {
    return Promise.resolve({
      ok: true,
      json: async () => ({ id: 7, customer_id: 9, status: 'authenticated', created_at: 't' }),
    })
  }
  return Promise.reject(new Error(`unexpected fetch: ${url}`))
}

function confirmPayload(): SecondConfirmPayload {
  return {
    conversation_id: 7,
    transaction_type: 'recharge',
    business_impact: {
      transaction_type: 'recharge',
      summary: '充值 100 元',
      plan_comparison: '当前：基础套餐 → 目标：不限量套餐',
      effective_time: '立即生效',
      contract_impact: '无合约影响',
      fee_change: '月费增加 50 元',
    },
    requested_at: 't',
  }
}

function reauthPayload(): ReauthRequiredPayload {
  return {
    ticket_id: 5,
    conversation_id: 7,
    message: '办理执行前需再次验证服务密码',
    requested_at: 't',
  }
}

async function mountChat(setup: () => void) {
  const pinia: Pinia = createPinia()
  setActivePinia(pinia)
  setup()
  const router: Router = createRouter({
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

/** 已认证 + 会话就绪（conversationId=7）。 */
function makeAuth() {
  useSessionStore().setAuthenticated({ accessToken: 'at', refreshToken: 'rt' }, '13800001234')
  useChatStore().conversationId = 7
}

beforeEach(() => {
  localStorage.clear()
  fetchMock.mockReset()
  fetchMock.mockImplementation(defaultFetch)
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ChatView — second-confirm-modal（States 矩阵）', () => {
  it('办理发起后弹出：summary + 结构化业务影响嵌套卡片 + 费用 tertiary 强调', async () => {
    const wrapper = await mountChat(() => {
      makeAuth()
      useChatStore().pendingConfirm = confirmPayload()
    })

    const modal = wrapper.find('[data-testid="second-confirm-modal"]')
    expect(modal.exists()).toBe(true)
    expect(modal.find('[data-testid="confirm-summary"]').text()).toBe('充值 100 元')

    const card = modal.find('[data-testid="impact-card"]')
    expect(card.exists()).toBe(true)
    const cardText = card.text()
    expect(cardText).toContain('套餐对比')
    expect(cardText).toContain('不限量套餐')
    expect(cardText).toContain('立即生效')
    expect(cardText).toContain('无合约影响')
    // 费用变化行 tertiary-tint-bg 强调（DESIGN.md §5 tertiary 强调底）
    const feeRow = card.find('.impact-card__row--fee')
    expect(feeRow.exists()).toBe(true)
    expect(feeRow.text()).toContain('月费增加 50 元')
  })

  it('确认办理：POST /transactions/confirm 入队并关闭 Modal', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url === '/api/conversations') {
        return {
          ok: true,
          json: async () => ({ id: 7, customer_id: 9, status: 'authenticated', created_at: 't' }),
        }
      }
      if (url === '/api/transactions/confirm') {
        return {
          ok: true,
          json: async () => ({
            id: 5,
            conversation_id: 7,
            ticket_type: 'transaction',
            status: 'pending',
            content: '充值 100 元',
          }),
        }
      }
      throw new Error(`unexpected fetch: ${url}`)
    })
    const wrapper = await mountChat(() => {
      makeAuth()
      useChatStore().pendingConfirm = confirmPayload()
    })

    await wrapper.find('[data-testid="confirm-submit"]').trigger('click')
    await flushPromises()

    const confirmCall = fetchMock.mock.calls.find(([url]) => url === '/api/transactions/confirm')
    expect(confirmCall).toBeDefined()
    const [, init] = confirmCall as [string, RequestInit]
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ conversation_id: 7, content: '充值 100 元' })
    expect(init.headers).toMatchObject({ Authorization: 'Bearer at' })

    expect(wrapper.find('[data-testid="second-confirm-modal"]').exists()).toBe(false)
  })

  it('取消：仅关闭 Modal，不发起 confirm', async () => {
    const wrapper = await mountChat(() => {
      makeAuth()
      useChatStore().pendingConfirm = confirmPayload()
    })

    await wrapper.find('[data-testid="confirm-cancel"]').trigger('click')
    await flushPromises()

    expect(fetchMock).not.toHaveBeenCalledWith('/api/transactions/confirm', expect.anything())
    expect(wrapper.find('[data-testid="second-confirm-modal"]').exists()).toBe(false)
  })

  it('确认失败：inline 错误文案 + Modal 保持打开', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url === '/api/conversations') {
        return {
          ok: true,
          json: async () => ({ id: 7, customer_id: 9, status: 'authenticated', created_at: 't' }),
        }
      }
      if (url === '/api/transactions/confirm') {
        return { ok: false, json: async () => ({ detail: '会话状态不可确认办理' }) }
      }
      throw new Error(`unexpected fetch: ${url}`)
    })
    const wrapper = await mountChat(() => {
      makeAuth()
      useChatStore().pendingConfirm = confirmPayload()
    })

    await wrapper.find('[data-testid="confirm-submit"]').trigger('click')
    await flushPromises()

    const err = wrapper.find('[data-testid="confirm-error"]')
    expect(err.exists()).toBe(true)
    expect(err.text()).toContain('会话状态不可确认办理')
    expect(wrapper.find('[data-testid="second-confirm-modal"]').exists()).toBe(true)
  })
})

describe('ChatView — reauth-modal（States 矩阵）', () => {
  it('执行前弹出：warning 提示 + 服务密码输入', async () => {
    const wrapper = await mountChat(() => {
      makeAuth()
      useChatStore().pendingReauth = reauthPayload()
    })

    const modal = wrapper.find('[data-testid="reauth-modal"]')
    expect(modal.exists()).toBe(true)
    expect(modal.find('[data-testid="reauth-message"]').text()).toBe('办理执行前需再次验证服务密码')
    expect(modal.find('[data-testid="reauth-password"]').exists()).toBe(true)
  })

  it('复核通过：/auth/reauth 取 execute_token → execute 执行并关闭 Modal', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url === '/api/conversations') {
        return {
          ok: true,
          json: async () => ({ id: 7, customer_id: 9, status: 'authenticated', created_at: 't' }),
        }
      }
      if (url === '/api/auth/reauth') {
        return { ok: true, json: async () => ({ execute_token: 'et', token_type: 'bearer' }) }
      }
      if (url === '/api/transactions/5/execute') {
        return {
          ok: true,
          json: async () => ({
            id: 5,
            conversation_id: 7,
            ticket_type: 'transaction',
            status: 'effective',
            content: '充值 100 元',
          }),
        }
      }
      throw new Error(`unexpected fetch: ${url}`)
    })
    const wrapper = await mountChat(() => {
      makeAuth()
      useChatStore().pendingReauth = reauthPayload()
    })

    await wrapper.find('[data-testid="reauth-password"]').setValue('123456')
    await wrapper.find('[data-testid="reauth-submit"]').trigger('click')
    await flushPromises()

    const reauthCall = fetchMock.mock.calls.find(([url]) => url === '/api/auth/reauth') as [
      string,
      RequestInit,
    ]
    expect(reauthCall).toBeDefined()
    expect(JSON.parse(String(reauthCall[1].body))).toEqual({ service_password: '123456' })
    expect(reauthCall[1].headers).toMatchObject({ Authorization: 'Bearer at' })

    const execCall = fetchMock.mock.calls.find(
      ([url]) => url === '/api/transactions/5/execute',
    ) as [string, RequestInit]
    expect(execCall).toBeDefined()
    expect(execCall[1].method).toBe('POST')
    expect(execCall[1].headers).toMatchObject({ Authorization: 'Bearer et' })

    expect(wrapper.find('[data-testid="reauth-modal"]').exists()).toBe(false)
  })

  it('复核失败（服务密码错误）：inline 错误文案 + Modal 保持打开', async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url === '/api/conversations') {
        return {
          ok: true,
          json: async () => ({ id: 7, customer_id: 9, status: 'authenticated', created_at: 't' }),
        }
      }
      if (url === '/api/auth/reauth') {
        return { ok: false, json: async () => ({ detail: '服务密码错误' }) }
      }
      throw new Error(`unexpected fetch: ${url}`)
    })
    const wrapper = await mountChat(() => {
      makeAuth()
      useChatStore().pendingReauth = reauthPayload()
    })

    await wrapper.find('[data-testid="reauth-password"]').setValue('0000')
    await wrapper.find('[data-testid="reauth-submit"]').trigger('click')
    await flushPromises()

    const err = wrapper.find('[data-testid="reauth-error"]')
    expect(err.exists()).toBe(true)
    expect(err.text()).toContain('服务密码错误')
    expect(wrapper.find('[data-testid="reauth-modal"]').exists()).toBe(true)
  })

  it('取消：仅关闭 Modal，不发起 reauth', async () => {
    const wrapper = await mountChat(() => {
      makeAuth()
      useChatStore().pendingReauth = reauthPayload()
    })

    await wrapper.find('[data-testid="reauth-cancel"]').trigger('click')
    await flushPromises()

    expect(fetchMock).not.toHaveBeenCalledWith('/api/auth/reauth', expect.anything())
    expect(wrapper.find('[data-testid="reauth-modal"]').exists()).toBe(false)
  })
})
