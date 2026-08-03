/**
 * agent-console active-chat 页 REST 客户端（坐席视角）。
 *
 * 后端契约核查（backend/app/agents/routes.py + schemas.py + conversation/ticket/routes.py）：
 *   坐席端点目前仅 /agents/login、/agents/status、/agents/queues 三个；
 *   会话消息历史（/conversations/{id}/messages 仅 CurrentCustomer → 坐席 401）、
 *   客户资料+账户信息（/customers/me 仅客户视角）、当前工单+创建工单（/tickets 仅客户）、
 *   执行复核（/auth/reauth + /transactions/{id}/execute 仅客户）全部缺失。
 *
 * TODO(backend #45, B12)：坐席视角 active-chat 数据契约缺口。v1 以本地 mock 数据源
 * 驱动 UI（模式同 queue store 的 MOCK_CALLBACK_TICKETS），#45 落地后各函数
 * 替换为真实 fetch（接口与类型不变），本段 mock 数据源随之删除。
 *
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（同 agents.ts）。
 */

import type { MessageNewPayload } from 'shared/events'

/** 坐席对话流消息：镜像 message.new payload，扩展 assistant_draft（助理后台起草草稿）。 */
export type AgentChatMessage = MessageNewPayload | DraftChatMessage

/** 助理草稿：未持久化，仅坐席可见，以 tertiary-tint-bg 气泡区分（PRD §active-chat 对话区段）。 */
export interface DraftChatMessage {
  id: number
  conversation_id: number
  source: 'assistant_draft'
  content: string
  created_at: string
}

/** 进行中会话视图（坐席视角会话头，镜像后端 #45 预期契约）。 */
export interface AgentConversationView {
  conversation_id: number
  status: string
  customer_id: number | null
  customer_phone: string | null
  handoff_reason: string | null
  /** 助理已尝试操作摘要（转接上下文，PRD §active-chat 右栏）。 */
  assistant_attempts: string[]
}

/** 客户资料（右栏）：认证客户含账户信息；访客仅联系方式（PRD 变体段「访客变体」）。 */
export interface AgentCustomerProfile {
  customer_id: number | null
  phone: string | null
  name: string | null
  authenticated: boolean
  contact_name: string | null
  contact_phone: string | null
  account_balance: string | null
  plan_name: string | null
  contract_expiry: string | null
}

/** 当前工单（右栏列表行，镜像 Ticket model 字段子集）。 */
export interface AgentTicket {
  id: number
  ticket_type: 'transaction' | 'ticketing'
  status: string
  content: string
}

/** 创建工单入参（Modal：工单类型 + 内容）。 */
export interface CreateTicketInput {
  ticket_type: 'transaction' | 'ticketing'
  content: string
}

/** 转接原因 → 展示文案（PRD 状态策略 / B8 HandoffReason 六类）。 */
export const HANDOFF_REASON_LABELS: Record<string, string> = {
  out_of_scope: '超出助理能力范围',
  transaction_failure: '办理失败',
  explicit_request: '用户明确要求转人工',
  negative_sentiment: '用户负面情绪',
  intent_loop: '意图循环未收敛',
  compliance_risk: '合规风险',
}

export function handoffReasonLabel(reason: string | null): string {
  if (!reason) return '转接原因未知'
  return HANDOFF_REASON_LABELS[reason] ?? reason
}

/** 工单状态 → 展示文案（按类型路由，两状态机并集，PRD line 288-292）。 */
export function ticketStatusLabel(ticket: AgentTicket): string {
  if (ticket.ticket_type === 'ticketing') {
    const map: Record<string, string> = {
      pending: '待派单',
      dispatched: '待处理',
      in_progress: '处理中',
      awaiting_confirmation: '待确认',
      closed: '已关闭',
      cancelled: '已取消',
    }
    return map[ticket.status] ?? ticket.status
  }
  const map: Record<string, string> = {
    pending: '待执行',
    processing: '执行中',
    effective: '已生效',
    failed: '执行失败',
    cancelled: '已取消',
  }
  return map[ticket.status] ?? ticket.status
}

/* ============ mock 数据源（TODO backend #45：落地后删除并改真实 fetch） ============ */

let _mockNextTicketId = 101

const MOCK_MESSAGES: AgentChatMessage[] = [
  {
    id: 1,
    conversation_id: 7,
    source: 'assistant',
    content: '您好，我是电信客服助理，请问有什么可以帮您？',
    created_at: '2026-08-03T01:00:00Z',
  },
  {
    id: 2,
    conversation_id: 7,
    source: 'user',
    content: '我想把现在的 5G 畅享套餐换成更便宜的档位',
    created_at: '2026-08-03T01:01:00Z',
  },
  {
    id: 3,
    conversation_id: 7,
    source: 'agent',
    content: '好的，我来帮您核实当前套餐与可选的变更方案',
    created_at: '2026-08-03T01:05:00Z',
  },
  {
    id: 4,
    conversation_id: 7,
    source: 'system',
    content: '人工客服已接入，为您服务',
    created_at: '2026-08-03T01:05:30Z',
  },
]

const MOCK_PROFILE: AgentCustomerProfile = {
  customer_id: 70,
  phone: '138****0001',
  name: '张**',
  authenticated: true,
  contact_name: null,
  contact_phone: null,
  account_balance: '58.60 元',
  plan_name: '5G 畅享套餐 129 元档',
  contract_expiry: '2027-06-30',
}

const MOCK_TICKETS: AgentTicket[] = [
  { id: 11, ticket_type: 'transaction', status: 'pending', content: '办理 10G 流量加装包' },
]

/**
 * 拉取进行中会话消息历史（按 created_at 升序；mock 固定返回演示对话）。
 * #45 落地后：GET /api/agents/conversations/{id}/messages（坐席 Bearer）。
 */
export async function listAgentMessages(
  conversationId: number,
  _token: string,
): Promise<AgentChatMessage[]> {
  void conversationId
  return MOCK_MESSAGES
}

/**
 * 拉取进行中会话视图；不存在返回 null（驱动空状态「暂无进行中会话」）。
 * #45 落地后：GET /api/agents/conversations/{id}（坐席 Bearer）。
 */
export async function fetchAgentConversation(
  conversationId: number,
  _token: string,
): Promise<AgentConversationView | null> {
  if (!conversationId) return null
  return {
    conversation_id: conversationId,
    status: 'handed_off',
    customer_id: 70,
    customer_phone: '138****0001',
    handoff_reason: 'explicit_request',
    assistant_attempts: ['已尝试查询套餐变更方案', '已尝试比对两档套餐差异'],
  }
}

/** 拉取客户资料（右栏标识卡 + 账户信息；加载变体骨架屏数据源）。 */
export async function fetchAgentCustomerProfile(
  _conversationId: number,
  _token: string,
): Promise<AgentCustomerProfile> {
  return MOCK_PROFILE
}

/** 拉取当前工单列表（右栏「当前工单」嵌套卡片）。 */
export async function listAgentTickets(
  _conversationId: number,
  _token: string,
): Promise<AgentTicket[]> {
  return [...MOCK_TICKETS]
}

/**
 * 创建工单（Modal 提交；成功返回新工单并追加到当前列表）。
 * #45 落地后：POST /api/agents/tickets（坐席 Bearer，creator_type=agent）。
 */
export async function createAgentTicket(
  _conversationId: number,
  input: CreateTicketInput,
  _token: string,
): Promise<AgentTicket> {
  const ticket: AgentTicket = {
    id: _mockNextTicketId++,
    ticket_type: input.ticket_type,
    status: 'pending',
    content: input.content,
  }
  MOCK_TICKETS.push(ticket)
  return ticket
}

/**
 * 服务密码复核通过后执行待执行办理工单（US-25；执行失败抛 Error 供 Modal 展示）。
 * #45 落地后：POST /api/agents/tickets/{id}/execute（复核密码校验待后端实现）。
 */
export async function executeAgentTicket(
  _conversationId: number,
  _ticketId: number,
  _servicePassword: string,
  _token: string,
): Promise<void> {
  return undefined
}
