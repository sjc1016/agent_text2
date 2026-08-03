import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

import TicketsView from '../views/TicketsView.vue'
import { useSessionStore } from '../stores/session'
import type { Ticket, TicketNotification } from '../api/tickets'

/**
 * #16 UI-C-4 循环：TicketsView（States 矩阵逐行验证）。
 *
 * 行序循环：default → empty → loading → unauthenticated。
 * 测行为不测像素：验证 data-testid 结构 + 可观察行为（列表渲染/展开收起/通知跳转/导航）。
 */

const fetchMock = vi.fn()

let router: Router

/** 挂载 TicketsView；setup 在组件挂载前于同一 pinia 上注入状态。 */
async function mountTickets(setup?: () => void) {
  const pinia = createPinia()
  setActivePinia(pinia)
  setup?.()
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/tickets', component: TicketsView },
      { path: '/auth', component: { template: '<div>auth</div>' } },
    ],
  })
  await router.push('/tickets')
  await router.isReady()
  const wrapper = mount(TicketsView, {
    global: { plugins: [router, pinia, ElementPlus] },
  })
  await flushPromises()
  return wrapper
}

/** 已认证：写入 JWT + 号码脱敏（session store 的 setAuthenticated 同 /auth 成功路径）。 */
function setAuthenticated() {
  useSessionStore().setAuthenticated({ accessToken: 'at', refreshToken: 'rt' }, '13800001234')
}

/** 工单 fixture（镜像 backend TicketOut 字段）。 */
function ticket(overrides: Partial<Ticket> = {}): Ticket {
  return {
    id: 1,
    conversation_id: 7,
    ticket_type: 'transaction',
    status: 'pending',
    content: '办理 10G 流量加装包',
    customer_id: 9,
    contact_name: null,
    contact_phone: null,
    creator_type: 'customer',
    creator_id: 9,
    created_at: '2026-08-03T01:00:00Z',
    ...overrides,
  }
}

/** 通知 fixture（镜像 backend NotificationOut，B13 后经 /api/notifications 返回）。 */
const NOTIFICATIONS_FIXTURE: TicketNotification[] = [
  {
    id: 1,
    ticket_id: 1,
    message: '您的办理工单已生效',
    read: false,
    created_at: '2026-08-03T02:00:00Z',
  },
  {
    id: 2,
    ticket_id: 2,
    message: '您的工单已派单',
    read: false,
    created_at: '2026-08-03T02:30:00Z',
  },
]

/** 按 URL 路由 fetch mock：/api/notifications 返回通知，其余 URL 返回工单列表。 */
function mockApi(tickets: Ticket[], notifications: TicketNotification[] = []) {
  fetchMock.mockImplementation((url: string) => {
    if (url === '/api/notifications') {
      return Promise.resolve({ ok: true, json: async () => notifications })
    }
    return Promise.resolve({ ok: true, json: async () => tickets })
  })
}

beforeEach(() => {
  localStorage.clear()
  fetchMock.mockReset()
  mockApi([ticket()])
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('TicketsView — default（States 矩阵 default）', () => {
  it('渲染页面标题 + 本人工单列表（类型标签 + 主文案 + 创建时间 + 状态徽章）', async () => {
    const wrapper = await mountTickets(() => {
      setAuthenticated()
      mockApi([
        ticket({
          id: 1,
          ticket_type: 'transaction',
          status: 'pending',
          content: '办理 10G 流量加装包',
        }),
        ticket({ id: 2, ticket_type: 'ticketing', status: 'closed', content: '宽带故障报修' }),
      ])
    })

    expect(wrapper.find('[data-testid="tickets-title"]').text()).toContain('我的工单')

    const rows = wrapper.findAll('[data-testid="ticket-row"]')
    expect(rows).toHaveLength(2)

    // 行一：办理类 + 主文案 + 状态徽章
    const first = rows[0]
    expect(first.text()).toContain('办理类')
    expect(first.text()).toContain('办理 10G 流量加装包')
    expect(first.text()).toContain('2026-08-03')
    const badge = first.find('[data-testid="ticket-status-badge"]')
    expect(badge.text()).toContain('待执行')

    // 行二：工单类 + 已关闭
    expect(rows[1].text()).toContain('工单类')
    expect(rows[1].text()).toContain('宽带故障报修')
    expect(rows[1].find('[data-testid="ticket-status-badge"]').text()).toContain('已关闭')
  })
})

describe('TicketsView — status-badge-variants（验收标准：状态徽章按状态机映射）', () => {
  /** 状态映射 fixture：办理类五态 + 工单类待派单/处理中/已关闭。 */
  const cases: Array<{ type: string; status: string; label: string; variant: string }> = [
    { type: 'transaction', status: 'pending', label: '待执行', variant: 'warning' },
    { type: 'ticketing', status: 'pending', label: '待派单', variant: 'warning' },
    { type: 'transaction', status: 'processing', label: '执行中', variant: 'info' },
    { type: 'ticketing', status: 'in_progress', label: '处理中', variant: 'info' },
    { type: 'transaction', status: 'effective', label: '已生效', variant: 'success' },
    { type: 'ticketing', status: 'closed', label: '已关闭', variant: 'success' },
    { type: 'transaction', status: 'failed', label: '已失败', variant: 'error' },
    { type: 'transaction', status: 'cancelled', label: '已取消', variant: 'neutral' },
  ]

  it.each(cases)(
    '$type/$status → $label 徽章 $variant',
    async ({ type, status, label, variant }) => {
      const wrapper = await mountTickets(() => {
        setAuthenticated()
        mockApi([ticket({ id: 1, ticket_type: type, status })])
      })

      const badge = wrapper.find('[data-testid="ticket-status-badge"]')
      expect(badge.text()).toContain(label)
      expect(badge.attributes('data-variant')).toBe(variant)
    },
  )
})

describe('TicketsView — expand-collapse（States 矩阵 default：点击行展开内联嵌套卡片）', () => {
  /** 列表 + 关联通知 fixture（通知经 B13 /api/notifications 真实端点 mock 返回）。 */
  const ticketsFixture = [
    ticket({
      id: 1,
      ticket_type: 'transaction',
      status: 'processing',
      content: '办理 10G 流量加装包',
    }),
    ticket({ id: 2, ticket_type: 'ticketing', status: 'closed', content: '宽带故障报修' }),
  ]

  it('点击行展开内联卡片（内容摘要 + 状态流转时间线 + 关联通知），再次点击收起', async () => {
    const wrapper = await mountTickets(() => {
      setAuthenticated()
      mockApi(ticketsFixture, NOTIFICATIONS_FIXTURE)
    })

    // 初始：无展开卡片
    expect(wrapper.find('[data-testid="ticket-detail-card"]').exists()).toBe(false)

    // 点击行一 → 展开：详情全文 + 时间线（已创建 + 当前状态）+ 关联通知
    await wrapper.findAll('[data-testid="ticket-row"]')[0].trigger('click')
    await flushPromises()

    const card = wrapper.find('[data-testid="ticket-detail-card"]')
    expect(card.exists()).toBe(true)
    expect(card.text()).toContain('办理 10G 流量加装包')
    expect(card.text()).toContain('已创建')
    expect(card.text()).toContain('执行中')
    expect(card.text()).toContain('您的办理工单已生效')

    // 再次点击同一行 → 收起
    await wrapper.findAll('[data-testid="ticket-row"]')[0].trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="ticket-detail-card"]').exists()).toBe(false)
  })

  it('点击另一行展开其详情，原展开行收起（单展开语义）', async () => {
    const wrapper = await mountTickets(() => {
      setAuthenticated()
      mockApi(ticketsFixture, NOTIFICATIONS_FIXTURE)
    })

    const rows = wrapper.findAll('[data-testid="ticket-row"]')
    await rows[0].trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="ticket-detail-card"]').text()).toContain(
      '办理 10G 流量加装包',
    )

    await rows[1].trigger('click')
    await flushPromises()

    // 仅一张展开卡（行二的）
    const cards = wrapper.findAll('[data-testid="ticket-detail-card"]')
    expect(cards).toHaveLength(1)
    expect(cards[0].text()).toContain('宽带故障报修')
  })
})

describe('TicketsView — notice-preview（States 矩阵 default：未读通知预览条）', () => {
  it('有未读通知时渲染预览条（文案 + 时间），点击展开对应工单', async () => {
    const wrapper = await mountTickets(() => {
      setAuthenticated()
      mockApi(
        [
          ticket({ id: 1, ticket_type: 'transaction', status: 'processing' }),
          ticket({ id: 2, ticket_type: 'ticketing', status: 'dispatched' }),
        ],
        NOTIFICATIONS_FIXTURE,
      )
    })

    // 预览条（semantic-info-tint-bg 卡片）：未读通知按时间倒序各含文案
    const bar = wrapper.find('[data-testid="notice-preview-bar"]')
    expect(bar.exists()).toBe(true)
    expect(bar.text()).toContain('您的办理工单已生效')
    expect(bar.text()).toContain('您的工单已派单')

    // 初始无展开卡片
    expect(wrapper.find('[data-testid="ticket-detail-card"]').exists()).toBe(false)

    // 点击「您的办理工单已生效」（ticket_id=1）→ 展开对应工单行
    const items = wrapper.findAll('[data-testid="notice-preview-item"]')
    const target = items.find((item) => item.text().includes('您的办理工单已生效'))
    expect(target).toBeDefined()
    await target!.trigger('click')
    await flushPromises()
    const card = wrapper.find('[data-testid="ticket-detail-card"]')
    expect(card.exists()).toBe(true)
    expect(card.text()).toContain('办理 10G 流量加装包')
  })
})

describe('TicketsView — empty（States 矩阵 empty：无工单空状态）', () => {
  it('无工单时显示居中空状态（插画 + 主文案 + 辅助文案），不渲染列表', async () => {
    const wrapper = await mountTickets(() => {
      setAuthenticated()
      mockApi([])
    })

    expect(wrapper.find('[data-testid="tickets-list"]').exists()).toBe(false)
    const empty = wrapper.find('[data-testid="tickets-empty"]')
    expect(empty.exists()).toBe(true)
    expect(empty.find('[data-testid="tickets-empty-illustration"]').exists()).toBe(true)
    expect(empty.text()).toContain('暂无工单')
    expect(empty.text()).toContain('办理业务或报修后将在此显示')
  })
})

describe('TicketsView — loading（States 矩阵 loading：列表骨架屏）', () => {
  it('加载中显示骨架屏（56px 行左图标 + 右两行文本条），加载完成切换列表', async () => {
    let resolveList!: (value: unknown) => void
    const pending = new Promise((resolve) => {
      resolveList = resolve
    })

    const wrapper = await mountTickets(() => {
      setAuthenticated()
      fetchMock.mockImplementation(() => pending)
    })

    // 加载中：骨架屏（aria-busy），列表/空态不渲染
    const skeleton = wrapper.find('[data-testid="tickets-skeleton"]')
    expect(skeleton.exists()).toBe(true)
    expect(skeleton.attributes('aria-busy')).toBe('true')
    expect(skeleton.findAll('[data-testid="skeleton-item"]').length).toBeGreaterThan(0)
    expect(wrapper.find('[data-testid="tickets-list"]').exists()).toBe(false)

    // 加载完成：骨架屏消失，列表渲染
    resolveList({ ok: true, json: async () => [ticket()] })
    await flushPromises()
    expect(wrapper.find('[data-testid="tickets-skeleton"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="ticket-row"]')).toHaveLength(1)
  })
})

describe('TicketsView — unauthenticated（States 矩阵 unauthenticated：未认证变体）', () => {
  it('未认证显示「请先认证查看工单」+「去认证」，不请求数据', async () => {
    const wrapper = await mountTickets(() => {
      // 不 setAuthenticated：session 无 token（访客）
    })

    expect(fetchMock).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="tickets-list"]').exists()).toBe(false)

    const unauth = wrapper.find('[data-testid="tickets-unauthenticated"]')
    expect(unauth.exists()).toBe(true)
    expect(unauth.text()).toContain('请先认证查看工单')

    const goAuth = unauth.find('[data-testid="go-auth-button"]')
    expect(goAuth.exists()).toBe(true)
    expect(goAuth.text()).toContain('去认证')
  })

  it('点击「去认证」跳转 /auth', async () => {
    const wrapper = await mountTickets()

    await wrapper.find('[data-testid="go-auth-button"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/auth')
  })
})
