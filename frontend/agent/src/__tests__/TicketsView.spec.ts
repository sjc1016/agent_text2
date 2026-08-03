import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import ElementPlus from 'element-plus'

import TicketsView from '../views/TicketsView.vue'
import { useAuthStore } from '../stores/auth'
import {
  listAgentTickets,
  dispatchTicket,
  executeTicket,
  closeTicket,
  createAgentTicket,
  type AgentTicket,
} from '../api/tickets'

/**
 * #22 UI-A-5 循环：TicketsView（States 矩阵逐行验证）。
 *
 * 行序循环：default → row-selected → empty → loading → no-result
 * （default 内部按验收标准细分：行内操作 US-24/27、复核 US-25、建单 US-23、回呼 US-29）。
 * 测行为不测像素：data-testid 结构 + 可观察行为。
 * 数据缺口：坐席视角工单端点缺失（backend #44/#45 B12）→ api mock 驱动（同 #20/#21 模式）。
 */

vi.mock('../api/tickets', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/tickets')>()
  return {
    ...actual,
    listAgentTickets: vi.fn(),
    dispatchTicket: vi.fn(),
    executeTicket: vi.fn(),
    closeTicket: vi.fn(),
    createAgentTicket: vi.fn(),
  }
})

const mockedListAgentTickets = vi.mocked(listAgentTickets)
const mockedDispatchTicket = vi.mocked(dispatchTicket)
const mockedExecuteTicket = vi.mocked(executeTicket)
const mockedCloseTicket = vi.mocked(closeTicket)
const mockedCreateAgentTicket = vi.mocked(createAgentTicket)

let router: Router

/** 测试工单工厂：覆盖两状态机各状态（PRD line 288-292）。 */
function ticket(overrides: Partial<AgentTicket> = {}): AgentTicket {
  return {
    id: 11,
    conversation_id: 7,
    ticket_type: 'ticketing',
    status: 'pending',
    content: '宽带故障报修',
    skill_group: 'fault',
    customer_phone: '138****0001',
    contact_name: null,
    contact_phone: null,
    created_at: '2026-08-03T01:00:00Z',
    ...overrides,
  }
}

/** 挂载 TicketsView；mock api 返回注入数据。 */
async function mountTickets(list: AgentTicket[]): Promise<{
  wrapper: ReturnType<typeof mount>
  router: Router
  pinia: Pinia
}> {
  const pinia: Pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.setAuthenticated({ accessToken: 'at', refreshToken: 'rt' }, '1001')
  mockedListAgentTickets.mockResolvedValue(list)
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/tickets', name: 'tickets', component: TicketsView },
      { path: '/tickets/:id', name: 'ticket-detail', component: { template: '<div>detail</div>' } },
      { path: '/queue', name: 'queue', component: { template: '<div>queue</div>' } },
    ],
  })
  await router.push('/tickets')
  await router.isReady()
  const wrapper = mount(TicketsView, {
    global: { plugins: [router, pinia, ElementPlus] },
  })
  await flushPromises()
  return { wrapper, router, pinia }
}

beforeEach(() => {
  localStorage.clear()
  mockedListAgentTickets.mockReset()
  mockedDispatchTicket.mockReset()
  mockedExecuteTicket.mockReset()
  mockedCloseTicket.mockReset()
  mockedCreateAgentTicket.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('TicketsView — default（PRD §tickets(agent-console) UI 设计描述）', () => {
  it('筛选栏（类型/状态/技能组 Select + 搜索 + 重置）+ 工单列表（ID/主文案/客户/时间/徽章/行内操作按钮组）', async () => {
    const { wrapper } = await mountTickets([
      ticket({ id: 11, ticket_type: 'ticketing', status: 'pending', content: '宽带故障报修' }),
      ticket({
        id: 12,
        ticket_type: 'transaction',
        status: 'pending',
        content: '办理 10G 流量加装包',
        skill_group: 'plan',
      }),
      ticket({
        id: 13,
        ticket_type: 'transaction',
        status: 'processing',
        content: '停机保号',
        skill_group: 'plan',
        customer_phone: '139****0002',
      }),
      ticket({ id: 14, ticket_type: 'ticketing', status: 'dispatched', content: '5G 套餐升级' }),
      ticket({
        id: 15,
        ticket_type: 'ticketing',
        status: 'awaiting_confirmation',
        content: '宽带移机',
      }),
      ticket({
        id: 16,
        ticket_type: 'ticketing',
        status: 'closed',
        content: '[回呼请求] 客户咨询套餐变更',
      }),
    ])

    // 顶栏标题「工单管理」（PRD：顶栏标题 H1 20px Neutral 800 600）
    const title = wrapper.find('[data-testid="tickets-title"]')
    expect(title.exists()).toBe(true)
    expect(title.text()).toBe('工单管理')

    // 筛选栏：类型 Select（办理类/工单类/全部）+ 状态 Select + 技能组 Select + 搜索框 + 重置
    const filters = wrapper.find('[data-testid="ticket-filters"]')
    expect(filters.exists()).toBe(true)
    expect(filters.find('[data-testid="filter-type"]').exists()).toBe(true)
    expect(filters.find('[data-testid="filter-status"]').exists()).toBe(true)
    expect(filters.find('[data-testid="filter-skill"]').exists()).toBe(true)
    expect(filters.find('[data-testid="filter-search"]').exists()).toBe(true)
    expect(filters.find('[data-testid="filter-reset"]').exists()).toBe(true)

    // 工单列表：6 行
    const rows = wrapper.findAll('[data-testid="ticket-row"]')
    expect(rows).toHaveLength(6)

    // 行内容：工单 ID（Caption）+ 主文案（类型 + 内容摘要 H3）+ 关联客户（号码脱敏）+ 创建时间 + 状态徽章
    const first = rows[0]
    expect(first.find('[data-testid="ticket-id"]').text()).toBe('#11')
    expect(first.find('[data-testid="ticket-title"]').text()).toContain('宽带故障报修')
    expect(first.find('[data-testid="ticket-customer"]').text()).toBe('138****0001')
    expect(first.find('[data-testid="ticket-status-badge"]').text()).toBe('待派单')

    // 类型图标：工单类 Tickets / 办理类 Finished（PRD §tickets 列表段）
    expect(rows[0].findComponent({ name: 'Tickets' }).exists()).toBe(true)
    expect(rows[1].findComponent({ name: 'Finished' }).exists()).toBe(true)
  })

  it('行内操作按钮组按状态显示：待派单→「派单」、待执行→「执行」、待确认→「关闭」、已派单→「查看」、已终结→无操作', async () => {
    const { wrapper } = await mountTickets([
      ticket({ id: 11, ticket_type: 'ticketing', status: 'pending' }), // 待派单 → 派单
      ticket({ id: 12, ticket_type: 'transaction', status: 'pending' }), // 待执行 → 执行
      ticket({ id: 13, ticket_type: 'ticketing', status: 'dispatched' }), // 已派单 → 查看
      ticket({ id: 14, ticket_type: 'ticketing', status: 'awaiting_confirmation' }), // 待确认 → 关闭
      ticket({ id: 15, ticket_type: 'ticketing', status: 'closed' }), // 已终结 → 无操作
    ])

    const rows = wrapper.findAll('[data-testid="ticket-row"]')

    // 待派单（工单类 pending）→ 主按钮「派单」
    expect(rows[0].find('[data-testid="row-action-dispatch"]').exists()).toBe(true)
    expect(rows[0].find('[data-testid="row-action-dispatch"]').text()).toBe('派单')

    // 待执行（办理类 pending）→ 主按钮「执行」
    expect(rows[1].find('[data-testid="row-action-execute"]').exists()).toBe(true)
    expect(rows[1].find('[data-testid="row-action-execute"]').text()).toBe('执行')

    // 已派单（dispatched）→ 文字按钮「查看」
    expect(rows[2].find('[data-testid="row-action-view"]').exists()).toBe(true)
    expect(rows[2].find('[data-testid="row-action-view"]').text()).toBe('查看')

    // 待确认（awaiting_confirmation）→ 描边按钮「关闭」
    expect(rows[3].find('[data-testid="row-action-close"]').exists()).toBe(true)
    expect(rows[3].find('[data-testid="row-action-close"]').text()).toBe('关闭')

    // 已终结（closed）→ 无行内操作
    expect(rows[4].find('[data-testid="row-action"]').exists()).toBe(false)
  })
})

describe('TicketsView — row-selected（PRD 页面清单 §tickets(agent-console) 列表行段）', () => {
  it('选中行渲染 primary-tint-bg-strong 背景 + 左侧 3px Primary 500 色条，点击另一行切换选中', async () => {
    const { wrapper } = await mountTickets([ticket({ id: 11 }), ticket({ id: 12 })])

    const rows = wrapper.findAll('[data-testid="ticket-row"]')
    await rows[0].trigger('click')
    await flushPromises()

    // 选中行：背景 primary-tint-bg-strong + 左侧 3px 色条
    const selected = wrapper.find('[data-testid="ticket-row"][data-selected="true"]')
    expect(selected.exists()).toBe(true)
    expect(selected.classes()).toContain('ticket-row--selected')

    // 点击另一行：选中切换
    await rows[1].trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="ticket-row"][data-selected="true"]').exists()).toBe(true)
    const selectedRows = wrapper.findAll('[data-testid="ticket-row"][data-selected="true"]')
    expect(selectedRows).toHaveLength(1)
    expect(selectedRows[0].attributes('data-id')).toBe('12')
  })
})

describe('TicketsView — empty（PRD §tickets(agent-console) 变体段「空状态」）', () => {
  it('无工单：居中 empty-state 插画 + 主文案「暂无工单」+ 辅助「调整筛选条件或创建新工单」', async () => {
    const { wrapper } = await mountTickets([])

    const empty = wrapper.find('[data-testid="tickets-empty"]')
    expect(empty.exists()).toBe(true)
    expect(empty.find('[data-testid="tickets-empty-illustration"]').exists()).toBe(true)
    expect(empty.text()).toContain('暂无工单')
    expect(empty.text()).toContain('调整筛选条件或创建新工单')
    expect(wrapper.find('[data-testid="tickets-list"]').exists()).toBe(false)
  })
})

describe('TicketsView — loading（PRD §tickets(agent-console) 变体段「加载变体」+ DESIGN.md §5 骨架屏）', () => {
  it('列表加载中显示骨架屏（aria-busy），完成后替换为工单列表', async () => {
    let resolveList!: (value: AgentTicket[]) => void
    mockedListAgentTickets.mockReturnValue(
      new Promise<AgentTicket[]>((resolve) => {
        resolveList = resolve
      }),
    )

    const pinia: Pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.setAuthenticated({ accessToken: 'at', refreshToken: 'rt' }, '1001')
    const testRouter = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/tickets', name: 'tickets', component: TicketsView }],
    })
    await testRouter.push('/tickets')
    await testRouter.isReady()
    const wrapper = mount(TicketsView, {
      global: { plugins: [testRouter, pinia, ElementPlus] },
    })
    await flushPromises()

    // 加载中：骨架屏 + aria-busy
    const skeleton = wrapper.find('[data-testid="tickets-skeleton"]')
    expect(skeleton.exists()).toBe(true)
    expect(skeleton.attributes('aria-busy')).toBe('true')
    expect(wrapper.find('[data-testid="tickets-list"]').exists()).toBe(false)

    // 加载完成：骨架屏移除，列表渲染
    resolveList([ticket()])
    await flushPromises()
    expect(wrapper.find('[data-testid="tickets-skeleton"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="ticket-row"]')).toHaveLength(1)
  })
})

describe('TicketsView — no-result（PRD §tickets(agent-console) 变体段「筛选无结果变体」）', () => {
  it('有工单但筛选无结果：空状态主文案「无匹配工单」+ 描边按钮「清除筛选」，点击后恢复列表', async () => {
    const { wrapper } = await mountTickets([
      ticket({ id: 11, ticket_type: 'ticketing', status: 'pending', content: '宽带故障报修' }),
    ])

    // 设置搜索关键词使结果为空
    await wrapper.find('[data-testid="filter-search"]').setValue('不存在的工单')
    await flushPromises()

    const noResult = wrapper.find('[data-testid="tickets-no-result"]')
    expect(noResult.exists()).toBe(true)
    expect(noResult.text()).toContain('无匹配工单')

    // 清除筛选 → 恢复列表
    await noResult.find('[data-testid="clear-filters"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="tickets-no-result"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="ticket-row"]')).toHaveLength(1)
  })
})

describe('TicketsView — 行内操作（US-24 派单 / US-24 关闭 / US-24 查看跳详情）', () => {
  it('待派单「派单」→ dispatchTicket 调用，成功后工单状态更新为已派单', async () => {
    mockedDispatchTicket.mockResolvedValue(ticket({ id: 11, status: 'dispatched' }))
    const { wrapper } = await mountTickets([ticket({ id: 11, status: 'pending' })])

    await wrapper.find('[data-testid="row-action-dispatch"]').trigger('click')
    await flushPromises()

    expect(mockedDispatchTicket).toHaveBeenCalledWith(11, 'at')
    expect(wrapper.find('[data-testid="ticket-status-badge"]').text()).toBe('已派单')
  })

  it('待确认「关闭」→ closeTicket 调用，成功后工单状态更新为已关闭', async () => {
    mockedCloseTicket.mockResolvedValue(ticket({ id: 11, status: 'closed' }))
    const { wrapper } = await mountTickets([
      ticket({ id: 11, ticket_type: 'ticketing', status: 'awaiting_confirmation' }),
    ])

    await wrapper.find('[data-testid="row-action-close"]').trigger('click')
    await flushPromises()

    expect(mockedCloseTicket).toHaveBeenCalledWith(11, 'at')
    expect(wrapper.find('[data-testid="ticket-status-badge"]').text()).toBe('已关闭')
  })

  it('已派单「查看」→ 跳转工单详情路由（ticket-detail）', async () => {
    const { wrapper, router } = await mountTickets([
      ticket({ id: 14, ticket_type: 'ticketing', status: 'dispatched' }),
    ])

    await wrapper.find('[data-testid="row-action-view"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('ticket-detail')
    expect(router.currentRoute.value.params.id).toBe('14')
  })
})

describe('TicketsView — 复核执行（US-25，待执行办理工单服务密码复核 Modal）', () => {
  it('待执行「执行」→ 服务密码复核 Modal，输入密码确认 → executeTicket 调用，Modal 关闭', async () => {
    mockedExecuteTicket.mockResolvedValue(
      ticket({ id: 12, ticket_type: 'transaction', status: 'processing' }),
    )
    const { wrapper } = await mountTickets([
      ticket({
        id: 12,
        ticket_type: 'transaction',
        status: 'pending',
        content: '办理 10G 流量加装包',
      }),
    ])

    // 点击执行 → 打开复核 Modal
    await wrapper.find('[data-testid="row-action-execute"]').trigger('click')
    const modal = wrapper.find('[data-testid="reauth-modal"]')
    expect(modal.exists()).toBe(true)
    expect(modal.text()).toContain('服务密码复核')
    expect(modal.text()).toContain('办理 10G 流量加装包')

    // 输入服务密码确认 → executeTicket 调用，Modal 关闭，状态更新为执行中
    await modal.find('[data-testid="reauth-password"]').setValue('123456')
    await modal.find('[data-testid="reauth-submit"]').trigger('click')
    await flushPromises()

    expect(mockedExecuteTicket).toHaveBeenCalledWith(12, '123456', 'at')
    expect(wrapper.find('[data-testid="reauth-modal"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="ticket-status-badge"]').text()).toBe('执行中')
  })
})

describe('TicketsView — 创建工单入口（US-23）', () => {
  it('「创建工单」→ Modal（类型 Select + 内容 textarea + 主按钮「创建」），提交后工单追加列表', async () => {
    mockedCreateAgentTicket.mockResolvedValue(
      ticket({ id: 99, ticket_type: 'ticketing', content: '宽带故障报修' }),
    )
    const { wrapper } = await mountTickets([ticket({ id: 11, status: 'closed' })])

    // 打开创建工单 Modal
    await wrapper.find('[data-testid="create-ticket-btn"]').trigger('click')
    const modal = wrapper.find('[data-testid="create-ticket-modal"]')
    expect(modal.exists()).toBe(true)
    expect(modal.find('[data-testid="ticket-type-select"]').exists()).toBe(true)
    expect(modal.find('[data-testid="ticket-content"]').exists()).toBe(true)

    // 选择类型 + 输入内容 → 提交
    await modal.find('[data-testid="ticket-type-select"]').setValue('ticketing')
    await modal.find('[data-testid="ticket-content"]').setValue('宽带故障报修')
    await modal.find('[data-testid="create-ticket-submit"]').trigger('click')
    await flushPromises()

    expect(mockedCreateAgentTicket).toHaveBeenCalledWith(
      { ticket_type: 'ticketing', content: '宽带故障报修' },
      'at',
    )
    expect(wrapper.find('[data-testid="create-ticket-modal"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="ticket-row"]')).toHaveLength(2)
  })
})

describe('TicketsView — 回呼请求工单（US-29）', () => {
  it('回呼请求工单（工单类 [回呼请求] 前缀 + dispatched）在列表中可见并可查看', async () => {
    const { wrapper, router } = await mountTickets([
      ticket({
        id: 20,
        ticket_type: 'ticketing',
        status: 'dispatched',
        content: '[回呼请求] 客户咨询套餐变更',
      }),
    ])

    // 列表中展示回呼请求工单 + 已派单徽章 + 「查看」操作
    const rows = wrapper.findAll('[data-testid="ticket-row"]')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('[回呼请求] 客户咨询套餐变更')
    expect(rows[0].find('[data-testid="ticket-status-badge"]').text()).toBe('已派单')
    await rows[0].find('[data-testid="row-action-view"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.params.id).toBe('20')
  })
})
