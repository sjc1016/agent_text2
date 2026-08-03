import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import ElementPlus from 'element-plus'

import TicketDetailView from '../views/TicketDetailView.vue'
import { useAuthStore } from '../stores/auth'
import {
  getAgentTicketDetail,
  dispatchTicketToGroup,
  executeTicket,
  closeTicket,
  cancelTicket,
  type AgentTicket,
  type AgentTicketDetail,
} from '../api/tickets'

/**
 * #23 UI-A-6 循环：TicketDetailView（States 矩阵逐行验证）。
 *
 * 行序循环：default → current-state-highlight → empty → loading → terminated
 * （default 内部按验收标准细分：基本信息/时间线/操作区/审计日志、操作交互 US-24/25）。
 * 测行为不测像素：data-testid 结构 + 可观察行为。
 * 数据缺口：坐席视角工单详情端点缺失（backend #44/#45 B12）→ api mock 驱动（同 #22 模式）。
 */

vi.mock('../api/tickets', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/tickets')>()
  return {
    ...actual,
    getAgentTicketDetail: vi.fn(),
    dispatchTicketToGroup: vi.fn(),
    executeTicket: vi.fn(),
    closeTicket: vi.fn(),
    cancelTicket: vi.fn(),
  }
})

const mockedGetAgentTicketDetail = vi.mocked(getAgentTicketDetail)
const mockedDispatchTicketToGroup = vi.mocked(dispatchTicketToGroup)
const mockedExecuteTicket = vi.mocked(executeTicket)
const mockedCloseTicket = vi.mocked(closeTicket)
const mockedCancelTicket = vi.mocked(cancelTicket)

let router: Router

/** 测试工单工厂（同 #22 TicketsView）。 */
function ticket(overrides: Partial<AgentTicket> = {}): AgentTicket {
  return {
    id: 11,
    conversation_id: 7,
    ticket_type: 'ticketing',
    status: 'pending',
    content: '宽带故障报修',
    skill_group: '故障报修组',
    customer_id: 10,
    customer_phone: '138****0001',
    contact_name: null,
    contact_phone: null,
    creator_type: 'customer',
    creator_id: null,
    created_at: '2026-08-03T01:00:00Z',
    ...overrides,
  }
}

/** 工单详情工厂（PRD §ticket-detail：基本信息 + 时间线 + 审计日志）。 */
function detail(overrides: Partial<AgentTicketDetail> = {}): AgentTicketDetail {
  return {
    ...ticket(),
    creator: '138****0001',
    timeline: [
      { status: 'pending', at: '2026-08-03T01:00:00Z', operator: '客户', is_current: true },
    ],
    audit_logs: [
      {
        id: 1,
        action: '工单创建',
        detail: '客户提交工单：宽带故障报修',
        created_at: '2026-08-03T01:00:00Z',
        is_key: false,
      },
    ],
    ...overrides,
  }
}

/** 挂载 TicketDetailView（路由 /tickets/11）；mock api 返回注入详情。 */
async function mountDetail(d: AgentTicketDetail): Promise<{
  wrapper: ReturnType<typeof mount>
  router: Router
  pinia: Pinia
}> {
  const pinia: Pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.setAuthenticated({ accessToken: 'at', refreshToken: 'rt' }, '1001')
  mockedGetAgentTicketDetail.mockResolvedValue(d)
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/tickets/:id', name: 'ticket-detail', component: TicketDetailView },
      { path: '/tickets', name: 'tickets', component: { template: '<div>tickets</div>' } },
    ],
  })
  await router.push('/tickets/11')
  await router.isReady()
  const wrapper = mount(TicketDetailView, {
    global: { plugins: [router, pinia, ElementPlus] },
  })
  await flushPromises()
  return { wrapper, router, pinia }
}

beforeEach(() => {
  localStorage.clear()
  mockedGetAgentTicketDetail.mockReset()
  mockedDispatchTicketToGroup.mockReset()
  mockedExecuteTicket.mockReset()
  mockedCloseTicket.mockReset()
  mockedCancelTicket.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('TicketDetailView — default（PRD §ticket-detail UI 设计描述）', () => {
  it('页头（返回 + 标题「工单详情」+ 状态徽章）+ 基本信息卡 + 时间线卡 + 审计日志卡', async () => {
    const { wrapper } = await mountDetail(
      detail({
        ticket_type: 'ticketing',
        status: 'pending',
        content: '宽带故障报修',
        timeline: [
          { status: 'pending', at: '2026-08-03T01:00:00Z', operator: '客户', is_current: true },
        ],
      }),
    )

    // 页头：返回图标按钮 + 标题「工单详情」（H1 20px）+ 右侧状态徽章
    expect(wrapper.find('[data-testid="detail-back"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="detail-title"]').text()).toBe('工单详情')
    expect(wrapper.find('[data-testid="detail-status-badge"]').text()).toBe('待派单')

    // 基本信息卡：H2 工单类型标题 + Body 内容全文 + Caption 创建时间/创建者/关联客户/技能组
    const info = wrapper.find('[data-testid="info-card"]')
    expect(info.find('[data-testid="info-type"]').text()).toBe('工单类')
    expect(info.find('[data-testid="info-content"]').text()).toBe('宽带故障报修')
    expect(info.find('[data-testid="info-meta"]').text()).toContain('2026-08-03 01:00')
    expect(info.find('[data-testid="info-meta"]').text()).toContain('创建者 138****0001')
    expect(info.find('[data-testid="info-meta"]').text()).toContain('关联客户 138****0001')
    expect(info.find('[data-testid="info-meta"]').text()).toContain('故障报修组')

    // 状态流转时间线卡：标题「状态流转」+ 节点（状态徽章 + 时间 + 操作人）
    const timeline = wrapper.find('[data-testid="timeline-card"]')
    expect(timeline.find('.card__title').text()).toBe('状态流转')
    const nodes = wrapper.findAll('[data-testid="timeline-node"]')
    expect(nodes).toHaveLength(1)
    expect(nodes[0].text()).toContain('待派单')
    expect(nodes[0].find('[data-testid="timeline-node-time"]').text()).toBe('2026-08-03 01:00')
    expect(nodes[0].find('[data-testid="timeline-node-operator"]').text()).toBe('客户')

    // 审计日志卡：标题「审计日志」+ 行（操作类型 + 详情 + 时间戳）
    const audit = wrapper.find('[data-testid="audit-card"]')
    expect(audit.find('.card__title').text()).toBe('审计日志')
    const rows = wrapper.findAll('[data-testid="audit-row"]')
    expect(rows).toHaveLength(1)
    expect(rows[0].find('[data-testid="audit-action"]').text()).toBe('工单创建')
    expect(rows[0].find('[data-testid="audit-detail"]').text()).toContain('宽带故障报修')
    expect(rows[0].find('[data-testid="audit-time"]').text()).toBe('2026-08-03 01:00')
  })

  it('审计日志按时间倒序展示，关键操作（服务密码认证）标记 Info 徽章', async () => {
    const { wrapper } = await mountDetail(
      detail({
        ticket_type: 'transaction',
        status: 'processing',
        content: '办理 10G 流量加装包',
        audit_logs: [
          {
            id: 1,
            action: '工单创建',
            detail: '客户提交办理工单：办理 10G 流量加装包',
            created_at: '2026-08-03T01:00:00Z',
            is_key: false,
          },
          {
            id: 2,
            action: '服务密码认证',
            detail: '坐席引导客户完成服务密码复核，验证通过',
            created_at: '2026-08-03T01:15:00Z',
            is_key: true,
          },
        ],
      }),
    )

    const rows = wrapper.findAll('[data-testid="audit-row"]')
    expect(rows).toHaveLength(2)
    // 倒序：最新（服务密码认证）在前
    expect(rows[0].find('[data-testid="audit-action"]').text()).toBe('服务密码认证')
    expect(rows[0].find('[data-testid="audit-time"]').text()).toBe('2026-08-03 01:15')
    // 关键操作 Info 徽章；普通操作无徽章
    expect(rows[0].find('[data-testid="audit-key-badge"]').exists()).toBe(true)
    expect(rows[0].find('[data-testid="audit-key-badge"]').text()).toBe('Info')
    expect(rows[1].find('[data-testid="audit-key-badge"]').exists()).toBe(false)
  })
})

describe('TicketDetailView — 操作区按状态（US-24：待派单派单 / 待执行执行复核 / 待确认关闭或取消）', () => {
  it('待派单（工单类 pending）→ 技能组 Select + 主按钮「派单到技能组」', async () => {
    const { wrapper } = await mountDetail(detail({ status: 'pending' }))

    const zone = wrapper.find('[data-testid="dispatch-zone"]')
    expect(zone.exists()).toBe(true)
    expect(zone.find('[data-testid="skill-group-select"]').exists()).toBe(true)
    expect(zone.find('[data-testid="dispatch-btn"]').text()).toBe('派单到技能组')
    expect(wrapper.find('[data-testid="execute-zone"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="confirm-zone"]').exists()).toBe(false)
  })

  it('待执行（办理类 pending）→ 主按钮「执行」触发服务密码复核 Modal（US-25）', async () => {
    const { wrapper } = await mountDetail(
      detail({ ticket_type: 'transaction', status: 'pending', content: '办理 10G 流量加装包' }),
    )

    const zone = wrapper.find('[data-testid="execute-zone"]')
    expect(zone.exists()).toBe(true)
    expect(zone.find('[data-testid="execute-btn"]').text()).toBe('执行')

    // 点击执行 → 复核 Modal（提示 + 密码输入框 + 主按钮「确认执行」）
    await zone.find('[data-testid="execute-btn"]').trigger('click')
    await flushPromises()
    const modal = wrapper.find('[data-testid="reauth-modal"]')
    expect(modal.exists()).toBe(true)
    expect(modal.text()).toContain('服务密码复核')
    expect(modal.text()).toContain('办理 10G 流量加装包')
    expect(modal.find('[data-testid="reauth-password"]').exists()).toBe(true)
    expect(modal.find('[data-testid="reauth-submit"]').text()).toBe('确认执行')
  })

  it('待确认（awaiting_confirmation）→ 主按钮「确认关闭」+ 描边按钮「取消工单」', async () => {
    const { wrapper } = await mountDetail(detail({ status: 'awaiting_confirmation' }))

    const zone = wrapper.find('[data-testid="confirm-zone"]')
    expect(zone.exists()).toBe(true)
    expect(zone.find('[data-testid="close-btn"]').text()).toBe('确认关闭')
    expect(zone.find('[data-testid="cancel-btn"]').text()).toBe('取消工单')
  })

  it('已终结（closed）→ 操作区无按钮显示「工单已终结」', async () => {
    const { wrapper } = await mountDetail(detail({ status: 'closed' }))

    expect(wrapper.find('[data-testid="terminated-hint"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="terminated-hint"]').text()).toBe('工单已终结')
    expect(wrapper.find('[data-testid="dispatch-zone"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="execute-zone"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="confirm-zone"]').exists()).toBe(false)
  })

  it('中间态（已派单 dispatched）→ 无可用操作提示', async () => {
    const { wrapper } = await mountDetail(detail({ status: 'dispatched' }))

    expect(wrapper.find('[data-testid="no-action-hint"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="no-action-hint"]').text()).toBe('当前状态暂无可用操作')
  })
})

describe('TicketDetailView — 操作交互（US-24 派单/关闭/取消、US-25 执行复核）', () => {
  it('派单到技能组：选择技能组 → dispatchTicketToGroup 调用，成功后状态徽章更新为已派单', async () => {
    mockedDispatchTicketToGroup.mockResolvedValue(ticket({ id: 11, status: 'dispatched' }))
    const { wrapper } = await mountDetail(detail({ status: 'pending' }))

    // 操作成功后 loadDetail 二次拉取返回已派单详情
    mockedGetAgentTicketDetail.mockResolvedValueOnce(
      detail({
        status: 'dispatched',
        skill_group: '故障报修组',
        timeline: [
          { status: 'pending', at: '2026-08-03T01:00:00Z', operator: '客户', is_current: false },
          {
            status: 'dispatched',
            at: '2026-08-03T01:05:00Z',
            operator: '坐席 1001',
            is_current: true,
          },
        ],
      }),
    )

    await wrapper.find('[data-testid="skill-group-select"]').setValue('故障报修组')
    await wrapper.find('[data-testid="dispatch-btn"]').trigger('click')
    await flushPromises()

    expect(mockedDispatchTicketToGroup).toHaveBeenCalledWith(11, '故障报修组', 'at')
    expect(wrapper.find('[data-testid="detail-status-badge"]').text()).toBe('已派单')
  })

  it('执行复核：输入服务密码确认 → executeTicket 调用，Modal 关闭，状态更新为执行中', async () => {
    mockedExecuteTicket.mockResolvedValue(
      ticket({ id: 11, ticket_type: 'transaction', status: 'processing' }),
    )
    const { wrapper } = await mountDetail(
      detail({ ticket_type: 'transaction', status: 'pending', content: '办理 10G 流量加装包' }),
    )

    mockedGetAgentTicketDetail.mockResolvedValueOnce(
      detail({ ticket_type: 'transaction', status: 'processing' }),
    )

    await wrapper.find('[data-testid="execute-btn"]').trigger('click')
    await wrapper.find('[data-testid="reauth-password"]').setValue('123456')
    await wrapper.find('[data-testid="reauth-submit"]').trigger('click')
    await flushPromises()

    expect(mockedExecuteTicket).toHaveBeenCalledWith(11, '123456', 'at')
    expect(wrapper.find('[data-testid="reauth-modal"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="detail-status-badge"]').text()).toBe('执行中')
  })

  it('确认关闭 → closeTicket 调用，成功后状态徽章更新为已关闭', async () => {
    mockedCloseTicket.mockResolvedValue(ticket({ id: 11, status: 'closed' }))
    const { wrapper } = await mountDetail(detail({ status: 'awaiting_confirmation' }))

    mockedGetAgentTicketDetail.mockResolvedValueOnce(detail({ status: 'closed' }))

    await wrapper.find('[data-testid="close-btn"]').trigger('click')
    await flushPromises()

    expect(mockedCloseTicket).toHaveBeenCalledWith(11, 'at')
    expect(wrapper.find('[data-testid="detail-status-badge"]').text()).toBe('已关闭')
  })

  it('取消工单 → cancelTicket 调用，成功后状态徽章更新为已取消', async () => {
    mockedCancelTicket.mockResolvedValue(ticket({ id: 11, status: 'cancelled' }))
    const { wrapper } = await mountDetail(detail({ status: 'awaiting_confirmation' }))

    mockedGetAgentTicketDetail.mockResolvedValueOnce(detail({ status: 'cancelled' }))

    await wrapper.find('[data-testid="cancel-btn"]').trigger('click')
    await flushPromises()

    expect(mockedCancelTicket).toHaveBeenCalledWith(11, 'at')
    expect(wrapper.find('[data-testid="detail-status-badge"]').text()).toBe('已取消')
  })

  it('返回按钮 → 跳转工单列表路由（tickets）', async () => {
    const { wrapper, router } = await mountDetail(detail())

    await wrapper.find('[data-testid="detail-back"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('tickets')
  })
})

describe('TicketDetailView — current-state-highlight（States 矩阵）', () => {
  it('时间线当前态节点 data-current=true + primary-tint-bg-strong 高亮', async () => {
    const { wrapper } = await mountDetail(
      detail({
        status: 'awaiting_confirmation',
        timeline: [
          { status: 'pending', at: '2026-08-03T01:00:00Z', operator: '客户', is_current: false },
          {
            status: 'dispatched',
            at: '2026-08-03T01:05:00Z',
            operator: '坐席 1001',
            is_current: false,
          },
          {
            status: 'in_progress',
            at: '2026-08-03T01:10:00Z',
            operator: '坐席 1001',
            is_current: false,
          },
          {
            status: 'awaiting_confirmation',
            at: '2026-08-03T01:15:00Z',
            operator: '坐席 1001',
            is_current: true,
          },
        ],
      }),
    )

    const nodes = wrapper.findAll('[data-testid="timeline-node"]')
    expect(nodes).toHaveLength(4)
    // 仅当前态节点高亮（primary-tint-bg-strong）
    const current = wrapper.findAll('[data-testid="timeline-node"][data-current="true"]')
    expect(current).toHaveLength(1)
    expect(current[0].classes()).toContain('timeline-node--current')
    expect(current[0].attributes('data-status')).toBe('awaiting_confirmation')
    expect(nodes[0].classes()).not.toContain('timeline-node--current')
  })
})

describe('TicketDetailView — empty（States 矩阵：审计日志无记录）', () => {
  it('审计日志无记录显示居中「暂无审计记录」', async () => {
    const { wrapper } = await mountDetail(detail({ audit_logs: [] }))

    expect(wrapper.find('[data-testid="audit-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="audit-empty"]').text()).toBe('暂无审计记录')
    expect(wrapper.find('[data-testid="audit-list"]').exists()).toBe(false)
  })
})

describe('TicketDetailView — loading（States 矩阵：时间线与日志骨架屏）', () => {
  it('加载中显示时间线与日志骨架屏（aria-busy），完成后替换为时间线与审计日志', async () => {
    let resolveDetail!: (v: AgentTicketDetail) => void
    mockedGetAgentTicketDetail.mockReturnValue(
      new Promise<AgentTicketDetail>((resolve) => {
        resolveDetail = resolve
      }),
    )

    const pinia: Pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore()
    auth.setAuthenticated({ accessToken: 'at', refreshToken: 'rt' }, '1001')
    const testRouter = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/tickets/:id', name: 'ticket-detail', component: TicketDetailView },
        { path: '/tickets', name: 'tickets', component: { template: '<div>tickets</div>' } },
      ],
    })
    await testRouter.push('/tickets/11')
    await testRouter.isReady()
    const wrapper = mount(TicketDetailView, {
      global: { plugins: [testRouter, pinia, ElementPlus] },
    })
    await flushPromises()

    // 加载中：时间线骨架 + 审计日志骨架 + aria-busy
    const timelineSkeleton = wrapper.find('[data-testid="timeline-skeleton"]')
    const auditSkeleton = wrapper.find('[data-testid="audit-skeleton"]')
    expect(timelineSkeleton.exists()).toBe(true)
    expect(auditSkeleton.exists()).toBe(true)
    expect(timelineSkeleton.attributes('aria-busy')).toBe('true')
    expect(wrapper.find('[data-testid="timeline"]').exists()).toBe(false)

    // 加载完成：骨架屏移除，时间线与审计日志渲染
    resolveDetail(detail())
    await flushPromises()
    expect(wrapper.find('[data-testid="timeline-skeleton"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="audit-skeleton"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="timeline-node"]')).toHaveLength(1)
    expect(wrapper.findAll('[data-testid="audit-row"]')).toHaveLength(1)
  })
})
