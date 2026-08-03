/**
 * agent-console active-chat 页 REST 客户端（坐席视角）。
 *
 * 契约（backend/app/agents/routes.py + schemas.py，B12 issue #44 / B14 issue #55）：
 *   GET  /api/agents/conversations/{id}               → ConversationViewOut（B14 AC4）
 *   GET  /api/agents/conversations/{id}/messages      → list[MessageOut]（B12 AC1）
 *   GET  /api/agents/conversations/{id}/tickets       → list[TicketOut]（B12 AC3）
 *   GET  /api/agents/customers/{customer_id}          → AgentCustomerProfileOut（B12 AC2）
 *   POST /api/agents/tickets                          → 201 TicketOut（B12 AC3）
 *   POST /api/agents/transactions/{ticket_id}/execute → TicketOut（B12 AC4）
 *
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（同 agents.ts）。
 * 边界（B14）：assistant_attempts（助理已尝试操作摘要）后端未提供（需 ticket_id 关联的
 * 审计扩展，另行 issue），前端置空数组，转接上下文卡仅渲染转接原因；详情页 audit_logs 同理。
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

/** 进行中会话视图（坐席视角会话头，镜像后端 ConversationViewOut）。 */
export interface AgentConversationView {
  conversation_id: number
  status: string
  customer_id: number | null
  customer_phone: string | null
  handoff_reason: string | null
  /** 助理已尝试操作摘要（转接上下文，PRD §active-chat 右栏）；B14 边界：后端未提供，置空。 */
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

/* ============ 真实 fetch（B12 #44 / B14 #55 已落地） ============ */

/** Bearer 请求头（坐席 JWT，来自 auth store `agent.auth`）。 */
function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

/** 非 2xx 响应收敛为 Error（detail 文案优先）。 */
async function expectOk(response: Response): Promise<Response> {
  if (!response.ok) {
    let detail = '请求失败'
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // 非 JSON 错误体：沿用默认文案
    }
    throw new Error(detail)
  }
  return response
}

/**
 * 拉取进行中会话视图；不存在返回 null（驱动空状态「暂无进行中会话」）。
 * GET /api/agents/conversations/{id}（B14 AC4；仅 handed_off 可见，否则 404 → null）。
 */
export async function fetchAgentConversation(
  conversationId: number,
  token: string,
): Promise<AgentConversationView | null> {
  const response = await fetch(`/api/agents/conversations/${conversationId}`, {
    headers: authHeaders(token),
  })
  if (response.status === 404) return null
  const body = (await expectOk(response).then((r) => r.json())) as {
    conversation_id: number
    status: string
    customer_id: number | null
    customer_phone: string | null
    handoff_reason: string | null
  }
  return {
    conversation_id: body.conversation_id,
    status: body.status,
    customer_id: body.customer_id,
    customer_phone: body.customer_phone,
    handoff_reason: body.handoff_reason,
    assistant_attempts: [], // B14 边界：后端未提供（另行 issue），转接上下文仅渲染转接原因
  }
}

/** 拉取进行中会话消息历史（按 created_at 升序）。GET /api/agents/conversations/{id}/messages（B12 AC1）。 */
export async function listAgentMessages(
  conversationId: number,
  token: string,
): Promise<AgentChatMessage[]> {
  const response = await expectOk(
    await fetch(`/api/agents/conversations/${conversationId}/messages`, {
      headers: authHeaders(token),
    }),
  )
  return (await response.json()) as AgentChatMessage[]
}

/**
 * 拉取认证客户资料 + 账户信息（US-21 右栏标识卡 + 账户信息块）。
 * GET /api/agents/customers/{customer_id}（B12 AC2；号码已脱敏，balance → 金额文案）。
 * 访客（无 Customer）不调用本函数：view 侧按 customer_id 为 null 本地构造访客资料卡。
 */
export async function fetchAgentCustomerProfile(
  customerId: number,
  token: string,
): Promise<AgentCustomerProfile> {
  const response = await expectOk(
    await fetch(`/api/agents/customers/${customerId}`, { headers: authHeaders(token) }),
  )
  const body = (await response.json()) as {
    id: number
    phone: string
    name: string | null
    authenticated: boolean
    balance: number
    plan_name: string | null
    contract_expiry_date: string | null
  }
  return {
    customer_id: body.id,
    phone: body.phone,
    name: body.name,
    authenticated: body.authenticated,
    contact_name: null,
    contact_phone: null,
    account_balance: `${body.balance.toFixed(2)} 元`,
    plan_name: body.plan_name,
    contract_expiry: body.contract_expiry_date,
  }
}

/** 拉取当前工单列表（右栏「当前工单」）。GET /api/agents/conversations/{id}/tickets（B12 AC3）。 */
export async function listAgentTickets(
  conversationId: number,
  token: string,
): Promise<AgentTicket[]> {
  const response = await expectOk(
    await fetch(`/api/agents/conversations/${conversationId}/tickets`, {
      headers: authHeaders(token),
    }),
  )
  return (await response.json()) as AgentTicket[]
}

/**
 * 创建工单（Modal 提交；成功返回新工单并追加到当前列表）。
 * POST /api/agents/tickets（B12 AC3；creator_type=agent，仅 handed_off 会话可建）。
 */
export async function createAgentTicket(
  conversationId: number,
  input: CreateTicketInput,
  token: string,
): Promise<AgentTicket> {
  const response = await expectOk(
    await fetch('/api/agents/tickets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
      body: JSON.stringify({
        conversation_id: conversationId,
        ticket_type: input.ticket_type,
        content: input.content,
      }),
    }),
  )
  return (await response.json()) as AgentTicket
}

/**
 * 服务密码复核通过后执行待执行办理工单（US-25；执行失败抛 Error 供 Modal 展示）。
 * POST /api/agents/transactions/{ticket_id}/execute（B12 AC4；服务密码校验失败 → 401）。
 */
export async function executeAgentTicket(
  _conversationId: number,
  ticketId: number,
  servicePassword: string,
  token: string,
): Promise<void> {
  const response = await expectOk(
    await fetch(`/api/agents/transactions/${ticketId}/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
      body: JSON.stringify({ service_password: servicePassword }),
    }),
  )
  await response.json() // TicketOut（调用方不消费返回值）
}
