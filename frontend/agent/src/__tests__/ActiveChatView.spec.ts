import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import ElementPlus from 'element-plus'

import ActiveChatView from '../views/ActiveChatView.vue'
import { useAuthStore } from '../stores/auth'
import {
  listAgentMessages,
  fetchAgentConversation,
  fetchAgentCustomerProfile,
  listAgentTickets,
  createAgentTicket,
  executeAgentTicket,
  type AgentChatMessage,
  type AgentConversationView,
  type AgentCustomerProfile,
  type AgentTicket,
} from '../api/activeChat'

/**
 * #21 UI-A-4 循环：ActiveChatView（States 矩阵逐行验证）。
 *
 * 行序循环：default → assistant-draft → visitor-variant → loading → empty
 * （default 内部按验收标准细分：对话 US-22 / 建单 US-23 / 复核 US-25 / 转回 US-26）。
 * 测行为不测像素：data-testid 结构 + 可观察行为。
 * 数据缺口：坐席视角 REST 端点缺失 → api mock 驱动（backend issue #45）；
 * 坐席 WS（take_over/message/state_transition）走后端 B9 真契约。
 */

vi.mock('../api/activeChat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/activeChat')>()
  return {
    ...actual,
    listAgentMessages: vi.fn(),
    fetchAgentConversation: vi.fn(),
    fetchAgentCustomerProfile: vi.fn(),
    listAgentTickets: vi.fn(),
    createAgentTicket: vi.fn(),
    executeAgentTicket: vi.fn(),
  }
})

/** vi.mock 工厂内无法引用外部变量：经 vi.hoisted 共享实例列表供断言。 */
const agentWsState = vi.hoisted(() => ({
  instances: [] as Array<{
    options: {
      getToken: () => string
      onEvent: (event: unknown) => void
      onOpen?: () => void
      onBrokenChange?: (broken: boolean) => void
    }
    connect: ReturnType<typeof vi.fn>
    close: ReturnType<typeof vi.fn>
    sendMessage: ReturnType<typeof vi.fn>
    sendTakeOver: ReturnType<typeof vi.fn>
    sendStateTransition: ReturnType<typeof vi.fn>
  }>,
}))

vi.mock('../api/agentWs', () => {
  class MockAgentWsClient {
    options: {
      getToken: () => string
      onEvent: (event: unknown) => void
      onOpen?: () => void
      onBrokenChange?: (broken: boolean) => void
    }
    connect: ReturnType<typeof vi.fn>
    close: ReturnType<typeof vi.fn>
    sendMessage: ReturnType<typeof vi.fn>
    sendTakeOver: ReturnType<typeof vi.fn>
    sendStateTransition: ReturnType<typeof vi.fn>

    constructor(options: {
      getToken: () => string
      onEvent: (event: unknown) => void
      onOpen?: () => void
      onBrokenChange?: (broken: boolean) => void
    }) {
      this.options = options
      this.connect = vi.fn(() => this.options.onOpen?.()) as ReturnType<typeof vi.fn>
      this.close = vi.fn()
      this.sendMessage = vi.fn()
      this.sendTakeOver = vi.fn()
      this.sendStateTransition = vi.fn()
      agentWsState.instances.push(this)
    }
  }
  return { AgentWsClient: MockAgentWsClient }
})

const mockedListAgentMessages = vi.mocked(listAgentMessages)
const mockedFetchAgentConversation = vi.mocked(fetchAgentConversation)
const mockedFetchAgentCustomerProfile = vi.mocked(fetchAgentCustomerProfile)
const mockedListAgentTickets = vi.mocked(listAgentTickets)
const mockedCreateAgentTicket = vi.mocked(createAgentTicket)
const mockedExecuteAgentTicket = vi.mocked(executeAgentTicket)

let router: Router

function message(
  id: number,
  source: AgentChatMessage['source'],
  content: string,
): AgentChatMessage {
  return {
    id,
    conversation_id: 7,
    source,
    content,
    created_at: '2026-08-03T01:00:00Z',
  } as AgentChatMessage
}

function conversation(overrides: Partial<AgentConversationView> = {}): AgentConversationView {
  return {
    conversation_id: 7,
    status: 'handed_off',
    customer_id: 70,
    customer_phone: '138****0001',
    handoff_reason: 'explicit_request',
    assistant_attempts: ['已尝试查询套餐变更方案'],
    ...overrides,
  }
}

function profile(overrides: Partial<AgentCustomerProfile> = {}): AgentCustomerProfile {
  return {
    customer_id: 70,
    phone: '138****0001',
    name: '张**',
    authenticated: true,
    contact_name: null,
    contact_phone: null,
    account_balance: '58.60 元',
    plan_name: '5G 畅享套餐 129 元档',
    contract_expiry: '2027-06-30',
    ...overrides,
  }
}

function ticket(overrides: Partial<AgentTicket> = {}): AgentTicket {
  return {
    id: 11,
    ticket_type: 'transaction',
    status: 'pending',
    content: '办理 10G 流量加装包',
    ...overrides,
  }
}

/** 挂载 ActiveChatView（默认 conversation_id=7）；mock api 返回注入数据。 */
async function mountActiveChat(conversationId: number | null = 7): Promise<{
  wrapper: ReturnType<typeof mount>
  router: Router
  pinia: Pinia
}> {
  const pinia: Pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.setAuthenticated({ accessToken: 'at', refreshToken: 'rt' }, '1001')
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/queue', name: 'queue', component: { template: '<div>queue</div>' } },
      { path: '/active-chat', name: 'active-chat', component: ActiveChatView },
    ],
  })
  await router.push(
    conversationId ? `/active-chat?conversation_id=${conversationId}` : '/active-chat',
  )
  await router.isReady()
  const wrapper = mount(ActiveChatView, {
    global: { plugins: [router, pinia, ElementPlus] },
  })
  await flushPromises()
  return { wrapper, router, pinia }
}

/** 最近一次创建的 AgentWsClient 实例（取 mock 实例）。 */
function lastWs() {
  const ws = agentWsState.instances[agentWsState.instances.length - 1]
  if (!ws) throw new Error('AgentWsClient 未被实例化')
  return ws
}

beforeEach(() => {
  localStorage.clear()
  agentWsState.instances = []
  mockedListAgentMessages.mockReset()
  mockedFetchAgentConversation.mockReset()
  mockedFetchAgentCustomerProfile.mockReset()
  mockedListAgentTickets.mockReset()
  mockedCreateAgentTicket.mockReset()
  mockedExecuteAgentTicket.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ActiveChatView — default（PRD §active-chat UI 设计描述）', () => {
  it('顶栏会话标题（号码脱敏）+ 转回助理按钮，左对话区四类气泡 + 输入区，右栏标识卡/账户信息/当前工单/转接上下文', async () => {
    mockedFetchAgentConversation.mockResolvedValue(conversation())
    mockedListAgentMessages.mockResolvedValue([
      message(1, 'assistant', '您好，请问有什么可以帮您？'),
      message(2, 'user', '我想更换套餐档位'),
      message(3, 'agent', '好的，我来帮您核实'),
      message(4, 'system', '人工客服已接入，为您服务'),
    ])
    mockedFetchAgentCustomerProfile.mockResolvedValue(profile())
    mockedListAgentTickets.mockResolvedValue([ticket()])
    const { wrapper } = await mountActiveChat()

    // 顶栏：会话标题（号码脱敏）+「转回助理」描边按钮
    const header = wrapper.find('[data-testid="active-chat-header"]')
    expect(header.exists()).toBe(true)
    expect(header.find('[data-testid="active-chat-title"]').text()).toBe('138****0001')
    expect(header.find('[data-testid="active-chat-transfer-btn"]').text()).toBe('转回助理')

    // 左对话区：四类消息气泡（data-source 区分）+ 输入区 + 创建工单入口
    const bubbles = wrapper.findAll('[data-testid="message-bubble"]')
    expect(bubbles).toHaveLength(4)
    expect(bubbles.map((b) => b.attributes('data-source'))).toEqual([
      'assistant',
      'user',
      'agent',
      'system',
    ])
    expect(bubbles[2].find('[data-testid="agent-tag"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="chat-textarea"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="chat-send"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="create-ticket-btn"]').exists()).toBe(true)

    // 右栏客户资料侧栏：标识卡（头像 + 号码脱敏 + 已认证徽章）
    const profileCard = wrapper.find('[data-testid="customer-profile-card"]')
    expect(profileCard.exists()).toBe(true)
    expect(profileCard.find('[data-testid="profile-avatar"]').exists()).toBe(true)
    expect(profileCard.find('[data-testid="profile-phone"]').text()).toBe('138****0001')
    expect(profileCard.find('[data-testid="profile-status-badge"]').text()).toBe('已认证')

    // 账户信息嵌套卡片：话费余额 + 套餐名 + 合约到期
    const account = wrapper.find('[data-testid="account-card"]')
    expect(account.exists()).toBe(true)
    expect(account.text()).toContain('58.60 元')
    expect(account.text()).toContain('5G 畅享套餐 129 元档')
    expect(account.text()).toContain('2027-06-30')

    // 当前工单嵌套卡片：工单内容 + 状态徽章（待执行）+ 执行按钮
    const ticketCard = wrapper.find('[data-testid="ticket-card"]')
    expect(ticketCard.exists()).toBe(true)
    expect(ticketCard.text()).toContain('办理 10G 流量加装包')
    expect(ticketCard.find('[data-testid="ticket-item-badge"]').text()).toBe('待执行')
    expect(ticketCard.find('[data-testid="ticket-execute-btn"]').exists()).toBe(true)

    // 转接上下文嵌套卡片：转接原因（展示文案）+ 助理已尝试操作摘要
    const context = wrapper.find('[data-testid="handoff-context-card"]')
    expect(context.exists()).toBe(true)
    expect(context.text()).toContain('用户明确要求转人工')
    expect(context.text()).toContain('已尝试查询套餐变更方案')
  })

  it('接入会话：WS 连接以坐席 token 打开，onOpen 发送 take_over（conversation_id）', async () => {
    mockedFetchAgentConversation.mockResolvedValue(conversation())
    mockedListAgentMessages.mockResolvedValue([message(1, 'assistant', '您好')])
    mockedFetchAgentCustomerProfile.mockResolvedValue(profile())
    mockedListAgentTickets.mockResolvedValue([])
    await mountActiveChat(7)

    const ws = lastWs()
    expect(ws.connect).toHaveBeenCalled()
    expect(ws.sendTakeOver).toHaveBeenCalledWith(7)
  })
})

describe('ActiveChatView — default 对话（US-22，坐席发消息）', () => {
  it('输入内容点击发送：WS sendMessage 出站，清空输入；message.new 回显为坐席气泡', async () => {
    mockedFetchAgentConversation.mockResolvedValue(conversation())
    mockedListAgentMessages.mockResolvedValue([
      message(1, 'assistant', '您好，请问有什么可以帮您？'),
    ])
    mockedFetchAgentCustomerProfile.mockResolvedValue(profile())
    mockedListAgentTickets.mockResolvedValue([])
    const { wrapper } = await mountActiveChat()

    const ws = lastWs()
    await wrapper.find('[data-testid="chat-textarea"]').setValue('我来帮您核对套餐变更')
    await wrapper.find('[data-testid="chat-send"]').trigger('click')

    expect(ws.sendMessage).toHaveBeenCalledWith(7, '我来帮您核对套餐变更')
    expect(
      (wrapper.find('[data-testid="chat-textarea"]').element as HTMLTextAreaElement).value,
    ).toBe('')

    // 后端回显 message.new（坐席自身发送的消息回推本连接）：追加为坐席气泡
    ws.options.onEvent({ event: 'message.new', data: message(5, 'agent', '我来帮您核对套餐变更') })
    await flushPromises()
    const bubbles = wrapper.findAll('[data-testid="message-bubble"]')
    expect(bubbles).toHaveLength(2)
    expect(bubbles[1].attributes('data-source')).toBe('agent')
    expect(bubbles[1].text()).toContain('我来帮您核对套餐变更')
  })
})

describe('ActiveChatView — default 建单（US-23，创建工单 Modal）', () => {
  it('「创建工单」打开 Modal，选择类型 + 输入内容提交 → createAgentTicket 调用，Modal 关闭，工单追加到当前工单', async () => {
    mockedFetchAgentConversation.mockResolvedValue(conversation())
    mockedListAgentMessages.mockResolvedValue([message(1, 'assistant', '您好')])
    mockedFetchAgentCustomerProfile.mockResolvedValue(profile())
    mockedListAgentTickets.mockResolvedValue([ticket()])
    mockedCreateAgentTicket.mockResolvedValue({
      id: 99,
      ticket_type: 'ticketing',
      status: 'pending',
      content: '宽带故障报修',
    })
    const { wrapper } = await mountActiveChat()

    // 打开 Modal
    await wrapper.find('[data-testid="create-ticket-btn"]').trigger('click')
    expect(wrapper.find('[data-testid="create-ticket-modal"]').exists()).toBe(true)

    // 选择类型 + 输入内容
    const modal = wrapper.find('[data-testid="create-ticket-modal"]')
    await modal.find('[data-testid="ticket-type-select"]').setValue('ticketing')
    await modal.find('[data-testid="ticket-content"]').setValue('宽带故障报修')

    // 提交：调用创建 API，Modal 关闭，工单追加
    await modal.find('[data-testid="create-ticket-submit"]').trigger('click')
    await flushPromises()

    expect(mockedCreateAgentTicket).toHaveBeenCalledWith(
      7,
      { ticket_type: 'ticketing', content: '宽带故障报修' },
      'at',
    )
    expect(wrapper.find('[data-testid="create-ticket-modal"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="ticket-item"]')).toHaveLength(2)
    expect(wrapper.find('[data-testid="ticket-card"]').text()).toContain('宽带故障报修')
  })
})

describe('ActiveChatView — default 复核（US-25，待执行工单服务密码复核 Modal）', () => {
  it('「执行」→ 服务密码复核 Modal，输入密码确认 → executeAgentTicket 调用，Modal 关闭', async () => {
    mockedFetchAgentConversation.mockResolvedValue(conversation())
    mockedListAgentMessages.mockResolvedValue([message(1, 'assistant', '您好')])
    mockedFetchAgentCustomerProfile.mockResolvedValue(profile())
    mockedListAgentTickets.mockResolvedValue([ticket()])
    mockedExecuteAgentTicket.mockResolvedValue(undefined)
    const { wrapper } = await mountActiveChat()

    // 点击执行 → 打开复核 Modal
    await wrapper.find('[data-testid="ticket-execute-btn"]').trigger('click')
    const modal = wrapper.find('[data-testid="reauth-modal"]')
    expect(modal.exists()).toBe(true)
    expect(modal.text()).toContain('服务密码复核')

    // 输入服务密码确认 → executeAgentTicket 调用，Modal 关闭
    await modal.find('[data-testid="reauth-password"]').setValue('123456')
    await modal.find('[data-testid="reauth-submit"]').trigger('click')
    await flushPromises()

    expect(mockedExecuteAgentTicket).toHaveBeenCalledWith(7, 11, '123456', 'at')
    expect(wrapper.find('[data-testid="reauth-modal"]').exists()).toBe(false)
  })
})

describe('ActiveChatView — default 转回（US-26，转回助理）', () => {
  it('「转回助理」→ WS sendStateTransition 出站 + 跳回 queue', async () => {
    mockedFetchAgentConversation.mockResolvedValue(conversation())
    mockedListAgentMessages.mockResolvedValue([message(1, 'assistant', '您好')])
    mockedFetchAgentCustomerProfile.mockResolvedValue(profile())
    mockedListAgentTickets.mockResolvedValue([])
    const { wrapper, router } = await mountActiveChat()

    const ws = lastWs()
    await wrapper.find('[data-testid="active-chat-transfer-btn"]').trigger('click')
    await flushPromises()

    expect(ws.sendStateTransition).toHaveBeenCalledWith(7)
    expect(router.currentRoute.value.name).toBe('queue')
  })
})

describe('ActiveChatView — assistant-draft（PRD §active-chat 对话区段，助理后台起草草稿气泡）', () => {
  it('草稿消息渲染 assistant_draft 气泡 + 「草稿」标签区分（tertiary-tint-bg 底）', async () => {
    mockedFetchAgentConversation.mockResolvedValue(conversation())
    mockedListAgentMessages.mockResolvedValue([
      message(1, 'assistant', '您好，请问有什么可以帮您？'),
      message(2, 'assistant_draft', '方案草稿：降档至 99 元档'),
    ])
    mockedFetchAgentCustomerProfile.mockResolvedValue(profile())
    mockedListAgentTickets.mockResolvedValue([])
    const { wrapper } = await mountActiveChat()

    const draftBubble = wrapper.find(
      '[data-testid="message-bubble"][data-source="assistant_draft"]',
    )
    expect(draftBubble.exists()).toBe(true)
    expect(draftBubble.classes()).toContain('bubble--assistant_draft')
    expect(draftBubble.find('[data-testid="draft-tag"]').exists()).toBe(true)
    expect(draftBubble.find('[data-testid="draft-tag"]').text()).toBe('草稿')
    expect(draftBubble.text()).toContain('方案草稿：降档至 99 元档')
  })
})

describe('ActiveChatView — visitor-variant（PRD §active-chat 变体段「访客变体」）', () => {
  it('访客资料卡显示「访客身份，仅记录联系方式」+ 联系方式字段，无账户信息卡', async () => {
    mockedFetchAgentConversation.mockResolvedValue(conversation())
    mockedListAgentMessages.mockResolvedValue([message(1, 'assistant', '您好')])
    mockedFetchAgentCustomerProfile.mockResolvedValue(
      profile({
        authenticated: false,
        contact_name: '李**',
        contact_phone: '139****0002',
        account_balance: null,
        plan_name: null,
        contract_expiry: null,
      }),
    )
    mockedListAgentTickets.mockResolvedValue([])
    const { wrapper } = await mountActiveChat()

    // 标识卡：访客徽章（neutral 变体）
    const badge = wrapper.find('[data-testid="profile-status-badge"]')
    expect(badge.text()).toBe('访客')
    expect(badge.attributes('data-variant')).toBe('neutral')

    // 访客提示 + 联系方式字段（联系人 / 联系电话）
    expect(wrapper.find('[data-testid="visitor-hint"]').text()).toBe('访客身份，仅记录联系方式')
    const contactCard = wrapper.find('[data-testid="contact-card"]')
    expect(contactCard.exists()).toBe(true)
    expect(contactCard.find('[data-testid="contact-name"]').text()).toBe('李**')
    expect(contactCard.find('[data-testid="contact-phone"]').text()).toBe('139****0002')

    // 账户信息卡为认证客户专属，访客不渲染
    expect(wrapper.find('[data-testid="account-card"]').exists()).toBe(false)
  })
})

describe('ActiveChatView — loading（PRD §active-chat 变体段「加载变体」+ DESIGN.md §5 骨架屏）', () => {
  it('客户资料加载中显示骨架屏（头像圆形 + 两行文本条），完成后替换为资料卡', async () => {
    mockedFetchAgentConversation.mockResolvedValue(conversation())
    mockedListAgentMessages.mockResolvedValue([message(1, 'assistant', '您好')])
    mockedListAgentTickets.mockResolvedValue([])
    let resolveProfile!: (value: AgentCustomerProfile) => void
    mockedFetchAgentCustomerProfile.mockReturnValue(
      new Promise<AgentCustomerProfile>((resolve) => {
        resolveProfile = resolve
      }),
    )
    const { wrapper } = await mountActiveChat()

    // 加载中：骨架屏（头像圆形 + 两行文本条），资料卡不渲染
    const skeleton = wrapper.find('[data-testid="profile-skeleton"]')
    expect(skeleton.exists()).toBe(true)
    expect(skeleton.attributes('aria-busy')).toBe('true')
    expect(skeleton.find('.profile-skeleton__avatar').exists()).toBe(true)
    expect(skeleton.find('.profile-skeleton__line--long').exists()).toBe(true)
    expect(skeleton.find('.profile-skeleton__line--short').exists()).toBe(true)
    expect(wrapper.find('[data-testid="customer-profile-card"]').exists()).toBe(false)

    // 加载完成：骨架屏移除，资料卡渲染
    resolveProfile(profile())
    await flushPromises()
    expect(wrapper.find('[data-testid="profile-skeleton"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="customer-profile-card"]').exists()).toBe(true)
  })
})

describe('ActiveChatView — empty（PRD §active-chat 变体段「空状态」）', () => {
  it('无进行中会话：居中 empty-state + 主文案 + 主按钮「前往待接入队列」→ 跳 queue', async () => {
    const { wrapper, router } = await mountActiveChat(null)

    // 空状态：主文案 + 主按钮（无会话 ID 时不拉取数据）
    const empty = wrapper.find('[data-testid="active-chat-empty"]')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('暂无进行中会话')
    expect(mockedFetchAgentConversation).not.toHaveBeenCalled()

    // 主按钮「前往待接入队列」→ 路由跳转 queue
    const goBtn = empty.find('[data-testid="go-queue-btn"]')
    expect(goBtn.exists()).toBe(true)
    expect(goBtn.text()).toBe('前往待接入队列')
    await goBtn.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('queue')
  })
})
