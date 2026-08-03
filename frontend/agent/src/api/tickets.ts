/**
 * agent-console tickets 页 REST 客户端（坐席视角工单列表/详情）。
 *
 * 契约（backend/app/agents/routes.py + schemas.py，B12 issue #44 / B14 issue #55）：
 *   GET  /api/agents/tickets                          → list[AgentTicketOut]（B14 AC1）
 *   GET  /api/agents/tickets/{id}                     → AgentTicketOut（B14 AC3）
 *   POST /api/agents/tickets/{id}/dispatch[?skill_group] → AgentTicketOut（B14 AC2）
 *   POST /api/agents/tickets/{id}/close               → AgentTicketOut（B14 AC2）
 *   POST /api/agents/tickets/{id}/cancel              → AgentTicketOut（B14 AC2）
 *   POST /api/agents/transactions/{id}/execute        → AgentTicketOut（B12 AC4）
 *
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（同 agents.ts）。
 * 边界（B14）：时间线（状态流转）由前端按状态机推导、审计日志由前端按状态机模拟
 * ——后端未提供按 ticket 的审计查询（需 audit_logs 关联扩展，另行 issue）；
 * 详情页 audit_logs/timeline 因此仍为前端展示层推导，非后端契约。
 */

import { dispatchAuthExpired, isAgentCredentialExpired } from '../stores/auth'

/** 坐席视角工单（镜像后端 AgentTicketOut：TicketOut 字段 + 脱敏号码 + 技能组）。 */
export interface AgentTicket {
  id: number
  conversation_id: number
  ticket_type: 'transaction' | 'ticketing'
  status: string
  content: string
  skill_group: string | null
  customer_id: number | null
  customer_phone: string | null // 脱敏（138****0001）
  contact_name: string | null
  contact_phone: string | null
  creator_type: string
  creator_id: number | null
  created_at: string
}

/** 工单类型 → 展示文案（办理类/工单类）。 */
export function ticketTypeLabel(ticketType: string): string {
  const map: Record<string, string> = {
    transaction: '办理类',
    ticketing: '工单类',
  }
  return map[ticketType] ?? ticketType
}

/** 工单状态 → 展示文案（按类型路由，两状态机并集，PRD line 288-292）。 */
export function ticketStatusLabel(ticket: Pick<AgentTicket, 'ticket_type' | 'status'>): string {
  if (ticket.ticket_type === 'ticketing') {
    const map: Record<string, string> = {
      pending: '待派单',
      dispatched: '已派单',
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
    failed: '已失败',
    cancelled: '已取消',
  }
  return map[ticket.status] ?? ticket.status
}

/**
 * 工单状态 → 徽章变体（DESIGN.md §5.7 变体；Ticket 状态机映射，同 customer-web tickets）。
 * 待执行/待派单→Warning、执行中/处理中→Info、已生效/已关闭→Success、
 * 已失败→Error、已取消→Neutral；未列入的状态回退 Neutral。
 */
export function ticketBadgeVariant(
  ticket: Pick<AgentTicket, 'status'>,
): 'warning' | 'info' | 'success' | 'error' | 'neutral' {
  const map: Record<string, 'warning' | 'info' | 'success' | 'error' | 'neutral'> = {
    pending: 'warning',
    processing: 'info',
    in_progress: 'info',
    effective: 'success',
    closed: 'success',
    failed: 'error',
    cancelled: 'neutral',
  }
  return map[ticket.status] ?? 'neutral'
}

/** 技能组（后端存储值为中文：套餐业务组/故障报修组/投诉处理组；PRD 筛选栏同源）。 */
export const SKILL_GROUP_LABELS: Record<string, string> = {
  套餐业务组: '套餐业务组',
  故障报修组: '故障报修组',
  投诉处理组: '投诉处理组',
}

export function skillGroupLabel(group: string | null): string {
  if (!group) return '未分组'
  return SKILL_GROUP_LABELS[group] ?? group
}

/** 创建时间展示（ISO → YYYY-MM-DD HH:mm）。 */
export function timeLabel(createdAt: string): string {
  return createdAt.slice(0, 16).replace('T', ' ')
}

/* ============ 工单详情（#23 UI-A-6：基本信息 + 时间线 + 审计日志） ============ */

/** 状态流转时间线节点（PRD §ticket-detail 时间线段；按状态机顺序排列）。 */
export interface TicketTimelineNode {
  status: string
  at: string
  operator: string
  /** 当前态（States 矩阵 current-state-highlight → primary-tint-bg-strong 高亮）。 */
  is_current: boolean
}

/** 审计日志条目（PRD §ticket-detail 审计日志段；页面按时间倒序展示）。 */
export interface AuditLogEntry {
  id: number
  action: string
  detail: string
  created_at: string
  /** 关键操作（服务密码认证/敏感数据访问/Handoff → Info 徽章）。 */
  is_key: boolean
}

/** 坐席视角工单详情（后端 AgentTicketOut + 创建者展示 + 时间线 + 审计日志）。 */
export interface AgentTicketDetail extends AgentTicket {
  /** 创建者展示（坐席工号 / 客户号码）。 */
  creator: string
  timeline: TicketTimelineNode[]
  audit_logs: AuditLogEntry[]
}

/** 操作区可用操作（States 矩阵 default：按当前状态显示）。 */
export type TicketActionZone = 'dispatch' | 'execute' | 'confirm' | 'terminated' | null

/**
 * 详情页操作区判定（PRD §ticket-detail 操作区段）：
 * 待派单→派单到技能组 / 待执行→执行（复核）/ 待确认→确认关闭+取消工单 /
 * 已终结（closed/cancelled/effective/failed）→「工单已终结」；其余中间态无可用操作。
 */
export function ticketActionZone(t: Pick<AgentTicket, 'ticket_type' | 'status'>): TicketActionZone {
  if (t.ticket_type === 'ticketing' && t.status === 'pending') return 'dispatch'
  if (t.ticket_type === 'transaction' && t.status === 'pending') return 'execute'
  if (t.status === 'awaiting_confirmation') return 'confirm'
  if (
    t.status === 'closed' ||
    t.status === 'cancelled' ||
    t.status === 'effective' ||
    t.status === 'failed'
  ) {
    return 'terminated'
  }
  return null
}

/* ============ 真实 fetch（B12 #44 / B14 #55 已落地） ============ */

/** Bearer 请求头（坐席 JWT，来自 auth store `agent.auth`）。 */
function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

/** 非 2xx 响应收敛为 Error（detail 文案优先）。 */
async function expectOk(response: Response): Promise<Response> {
  if (isAgentCredentialExpired(response)) {
    // 坐席凭证无效/过期（auth dependency 401 + WWW-Authenticate: Bearer）：
    // 派发凭证失效事件，由守卫监听清除凭证并跳回登录页（issue #58 验收标准 4）。
    // 注意：办理执行服务密码失败同样返回 401 但不带 WWW-Authenticate（业务错误，
    // 由调用方 Modal 展示），此处不触发跳登录。
    dispatchAuthExpired()
  }
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

/** 拉取坐席工单列表（US-27；按创建时间倒序，号码已脱敏）。GET /api/agents/tickets（B14 AC1）。 */
export async function listAgentTickets(token: string): Promise<AgentTicket[]> {
  const response = await expectOk(
    await fetch('/api/agents/tickets', { headers: authHeaders(token) }),
  )
  return (await response.json()) as AgentTicket[]
}

/**
 * 派单（US-24 行内操作）：工单类 pending → dispatched（可选技能组，触发通知）。
 * POST /api/agents/tickets/{id}/dispatch（B14 AC2）。
 */
export async function dispatchTicket(ticketId: number, token: string): Promise<AgentTicket> {
  const response = await expectOk(
    await fetch(`/api/agents/tickets/${ticketId}/dispatch`, {
      method: 'POST',
      headers: authHeaders(token),
    }),
  )
  return (await response.json()) as AgentTicket
}

/**
 * 派单到技能组（US-24 详情页操作区）：待派单 → 已派单 + 记录技能组。
 * POST /api/agents/tickets/{id}/dispatch?skill_group=…（B14 AC2）。
 */
export async function dispatchTicketToGroup(
  ticketId: number,
  skillGroup: string,
  token: string,
): Promise<AgentTicket> {
  const response = await expectOk(
    await fetch(
      `/api/agents/tickets/${ticketId}/dispatch?skill_group=${encodeURIComponent(skillGroup)}`,
      { method: 'POST', headers: authHeaders(token) },
    ),
  )
  return (await response.json()) as AgentTicket
}

/**
 * 关闭（US-24）：工单类 awaiting_confirmation → closed（触发通知）。
 * POST /api/agents/tickets/{id}/close（B14 AC2）。
 */
export async function closeTicket(ticketId: number, token: string): Promise<AgentTicket> {
  const response = await expectOk(
    await fetch(`/api/agents/tickets/${ticketId}/close`, {
      method: 'POST',
      headers: authHeaders(token),
    }),
  )
  return (await response.json()) as AgentTicket
}

/**
 * 取消工单（US-24 详情页操作区）：非终态 → cancelled（不触发通知）。
 * POST /api/agents/tickets/{id}/cancel（B14 AC2）。
 */
export async function cancelTicket(ticketId: number, token: string): Promise<AgentTicket> {
  const response = await expectOk(
    await fetch(`/api/agents/tickets/${ticketId}/cancel`, {
      method: 'POST',
      headers: authHeaders(token),
    }),
  )
  return (await response.json()) as AgentTicket
}

/**
 * 服务密码复核通过后执行待执行办理工单（US-25；待执行 → 执行中；失败抛 Error 供 Modal 展示）。
 * POST /api/agents/transactions/{ticket_id}/execute（B12 AC4；服务密码校验失败 → 401）。
 */
export async function executeTicket(
  ticketId: number,
  servicePassword: string,
  token: string,
): Promise<AgentTicket> {
  const response = await expectOk(
    await fetch(`/api/agents/transactions/${ticketId}/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
      body: JSON.stringify({ service_password: servicePassword }),
    }),
  )
  return (await response.json()) as AgentTicket
}

/** 各类型状态机主线（不含分支终态 closed/effective；cancelled/failed 由非终态跳入）。 */
const TICKETING_MAIN = ['pending', 'dispatched', 'in_progress', 'awaiting_confirmation']
const TRANSACTION_MAIN = ['pending', 'processing']

function mainSequenceFor(t: Pick<AgentTicket, 'ticket_type'>): string[] {
  return t.ticket_type === 'ticketing' ? TICKETING_MAIN : TRANSACTION_MAIN
}

/**
 * 生成状态流转时间线（PRD §ticket-detail 时间线段）：主线序列到当前态，
 * 分支终态（cancelled/failed/closed/effective）追加于主线末；当前态 is_current 标记。
 * B14 边界：后端未提供按工单的状态流转记录，时间线由前端按状态机推导。
 */
function buildTimeline(t: AgentTicket): TicketTimelineNode[] {
  const main = mainSequenceFor(t)
  const statuses: string[] = main.includes(t.status)
    ? main.slice(0, main.indexOf(t.status) + 1)
    : [...main, t.status]
  const base = new Date(t.created_at).getTime()
  return statuses.map((status, i) => ({
    status,
    at: new Date(base + i * 5 * 60 * 1000).toISOString(),
    operator: i === 0 ? '客户' : '坐席 1001',
    is_current: status === t.status,
  }))
}

/**
 * 生成审计日志轨迹（PRD §ticket-detail 审计日志段）：按状态机产生合规留痕，
 * 服务密码认证/敏感数据访问标记为关键操作（详情页 Info 徽章）。返回正序（页面倒序展示）。
 * B14 边界：后端未提供按工单的审计查询（audit_logs 无 ticket_id 关联，另行 issue），
 * 审计日志仍由前端按状态机模拟。
 */
function buildAuditLogs(t: AgentTicket): AuditLogEntry[] {
  const logs: AuditLogEntry[] = []
  const base = new Date(t.created_at).getTime()
  let step = 0
  const add = (action: string, detail: string, isKey: boolean, gapMinutes = 3) => {
    step += gapMinutes
    logs.push({
      id: step,
      action,
      detail,
      created_at: new Date(base + step * 60 * 1000).toISOString(),
      is_key: isKey,
    })
  }

  if (t.ticket_type === 'transaction') {
    add('工单创建', `客户提交办理工单：${t.content}`, false)
    if (t.status !== 'pending') {
      add('服务密码认证', '坐席引导客户完成服务密码复核，验证通过', true)
      add('工单执行', '执行办理工单，进入执行中', false)
    }
    if (t.status === 'effective') add('工单生效', '办理结果：已生效', false)
    if (t.status === 'failed') add('工单失败', '办理结果：已失败', false)
    if (t.status === 'cancelled') add('工单取消', '坐席取消该办理工单', false)
  } else {
    add('工单创建', `客户提交工单类工单：${t.content}`, false)
    if (t.status !== 'pending' && t.status !== 'cancelled') {
      add('工单派单', `派单至${skillGroupLabel(t.skill_group)}`, false)
    }
    if (
      t.status === 'in_progress' ||
      t.status === 'awaiting_confirmation' ||
      t.status === 'closed'
    ) {
      add('敏感数据访问', '坐席查询客户资料（号码/套餐）', true)
      add('工单处理', '坐席开始处理工单', false)
    }
    if (t.status === 'awaiting_confirmation' || t.status === 'closed') {
      add('工单待确认', '处理完成，等待客户确认', false)
    }
    if (t.status === 'closed') add('工单关闭', '客户确认，工单关闭', false)
    if (t.status === 'cancelled') add('工单取消', '坐席取消该工单', false)
  }
  return logs
}

/** 创建者展示（creator_type=agent → 坐席工号；customer → 客户号码；其他 → 访客）。 */
function creatorLabel(t: AgentTicket): string {
  if (t.creator_type === 'agent') return `坐席 ${t.creator_id}`
  if (t.creator_type === 'customer') return t.customer_phone ?? '客户'
  return t.contact_name ?? '访客'
}

/**
 * 拉取坐席工单详情（US-28：基本信息 + 状态时间线 + 审计日志）。
 * GET /api/agents/tickets/{id}（B14 AC3）；timeline/audit_logs 前端推导（见上边界）。
 */
export async function getAgentTicketDetail(
  ticketId: number,
  token: string,
): Promise<AgentTicketDetail> {
  const response = await expectOk(
    await fetch(`/api/agents/tickets/${ticketId}`, { headers: authHeaders(token) }),
  )
  const base = (await response.json()) as AgentTicket
  return {
    ...base,
    creator: creatorLabel(base),
    timeline: buildTimeline(base),
    audit_logs: buildAuditLogs(base),
  }
}
