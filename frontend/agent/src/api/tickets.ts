/**
 * agent-console tickets 页 REST 客户端（坐席视角工单列表）。
 *
 * 后端契约核查（backend/app/ticket/routes.py + schemas.py）：
 *   B7（#10）仅提供客户视角端点：POST/GET/PATCH /tickets（CurrentCustomer Bearer）。
 *   坐席视角工单端点缺失（backend #44/#45，B12），与 #20/#21 模式一致：
 *   v1 以本地 mock 数据源驱动 UI（接口与类型保持镜像后端 TicketOut + 坐席展示所需字段），
 *   #44/#45 落地后各函数替换为真实 fetch（GET /api/agents/tickets、PATCH 状态流转、执行复核）。
 *
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（同 agents.ts）。
 */

/** 坐席视角工单（镜像 backend TicketOut + 关联客户号码脱敏 + skill_group 技能组）。 */
export interface AgentTicket {
  id: number
  conversation_id: number
  ticket_type: 'transaction' | 'ticketing'
  status: string
  content: string
  skill_group: string | null
  customer_phone: string | null
  contact_name: string | null
  contact_phone: string | null
  created_at: string
}

/** 创建工单入参（US-23：工单类型 + 内容，PRD 建单 Modal 两字段）。 */
export interface CreateTicketInput {
  ticket_type: 'transaction' | 'ticketing'
  content: string
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

/** 技能组 → 展示文案（PRD 筛选栏技能组：套餐业务组/故障报修组/投诉处理组）。 */
export const SKILL_GROUP_LABELS: Record<string, string> = {
  plan: '套餐业务组',
  fault: '故障报修组',
  complaint: '投诉处理组',
}

export function skillGroupLabel(group: string | null): string {
  if (!group) return '未分组'
  return SKILL_GROUP_LABELS[group] ?? group
}

/** 创建时间展示（ISO → YYYY-MM-DD HH:mm）。 */
export function timeLabel(createdAt: string): string {
  return createdAt.slice(0, 16).replace('T', ' ')
}

/* ============ mock 数据源（TODO backend #44/#45：落地后删除并改真实 fetch） ============ */

/** 当前列表快照：行内操作成功后原地替换对应工单（状态更新由 mock 返回最新对象）。 */
let _mockTickets: AgentTicket[] = [
  {
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
  },
  {
    id: 12,
    conversation_id: 7,
    ticket_type: 'transaction',
    status: 'pending',
    content: '办理 10G 流量加装包',
    skill_group: 'plan',
    customer_phone: '138****0001',
    contact_name: null,
    contact_phone: null,
    created_at: '2026-08-03T01:05:00Z',
  },
  {
    id: 13,
    conversation_id: 7,
    ticket_type: 'transaction',
    status: 'processing',
    content: '停机保号',
    skill_group: 'plan',
    customer_phone: '139****0002',
    contact_name: null,
    contact_phone: null,
    created_at: '2026-08-03T01:10:00Z',
  },
  {
    id: 14,
    conversation_id: 8,
    ticket_type: 'ticketing',
    status: 'dispatched',
    content: '5G 套餐升级咨询',
    skill_group: 'plan',
    customer_phone: '158****0013',
    contact_name: null,
    contact_phone: null,
    created_at: '2026-08-03T02:00:00Z',
  },
  {
    id: 15,
    conversation_id: 8,
    ticket_type: 'ticketing',
    status: 'awaiting_confirmation',
    content: '宽带移机',
    skill_group: 'fault',
    customer_phone: '158****0013',
    contact_name: null,
    contact_phone: null,
    created_at: '2026-08-03T02:20:00Z',
  },
  {
    id: 16,
    conversation_id: 9,
    ticket_type: 'ticketing',
    status: 'dispatched',
    content: '[回呼请求] 客户咨询套餐变更',
    skill_group: 'plan',
    customer_phone: '136****0088',
    contact_name: null,
    contact_phone: null,
    created_at: '2026-08-03T02:30:00Z',
  },
]

let _mockNextTicketId = 100

function replaceMock(ticket: AgentTicket): AgentTicket {
  _mockTickets = _mockTickets.map((t) => (t.id === ticket.id ? ticket : t))
  return ticket
}

/**
 * 拉取坐席工单列表（US-27；按创建时间倒序，号码已脱敏）。
 * #44/#45 落地后：GET /api/agents/tickets（坐席 Bearer）。
 */
export async function listAgentTickets(_token: string): Promise<AgentTicket[]> {
  return _mockTickets.slice().sort((a, b) => b.created_at.localeCompare(a.created_at))
}

/**
 * 派单（US-24）：待派单（工单类 pending）→ 已派单。
 * #44/#45 落地后：POST /api/agents/tickets/{id}/dispatch（坐席 Bearer）。
 */
export async function dispatchTicket(ticketId: number, _token: string): Promise<AgentTicket> {
  const current = _mockTickets.find((t) => t.id === ticketId)
  if (!current) throw new Error('工单不存在')
  return replaceMock({ ...current, status: 'dispatched' })
}

/**
 * 关闭（US-24）：待确认（awaiting_confirmation）→ 已关闭。
 * #44/#45 落地后：POST /api/agents/tickets/{id}/close（坐席 Bearer）。
 */
export async function closeTicket(ticketId: number, _token: string): Promise<AgentTicket> {
  const current = _mockTickets.find((t) => t.id === ticketId)
  if (!current) throw new Error('工单不存在')
  return replaceMock({ ...current, status: 'closed' })
}

/**
 * 服务密码复核通过后执行待执行办理工单（US-25；待执行 → 执行中）。
 * #44/#45 落地后：POST /api/agents/tickets/{id}/execute（复核密码校验待后端实现）。
 */
export async function executeTicket(
  ticketId: number,
  _servicePassword: string,
  _token: string,
): Promise<AgentTicket> {
  const current = _mockTickets.find((t) => t.id === ticketId)
  if (!current) throw new Error('工单不存在')
  return replaceMock({ ...current, status: 'processing' })
}

/**
 * 创建工单（US-23）：坐席建单，默认 pending 入队。
 * #44/#45 落地后：POST /api/agents/tickets（坐席 Bearer，creator_type=agent）。
 */
export async function createAgentTicket(
  input: CreateTicketInput,
  _token: string,
): Promise<AgentTicket> {
  const ticket: AgentTicket = {
    id: _mockNextTicketId++,
    conversation_id: 0,
    ticket_type: input.ticket_type,
    status: 'pending',
    content: input.content,
    skill_group: null,
    customer_phone: null,
    contact_name: null,
    contact_phone: null,
    created_at: new Date().toISOString(),
  }
  _mockTickets = [ticket, ..._mockTickets]
  return ticket
}
