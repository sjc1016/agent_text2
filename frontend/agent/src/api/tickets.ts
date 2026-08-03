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

/** 坐席视角工单详情（镜像 backend TicketOut + 创建者展示 + 时间线 + 审计日志）。 */
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
  {
    id: 17,
    conversation_id: 9,
    ticket_type: 'ticketing',
    status: 'closed',
    content: '宽带移机已完成',
    skill_group: 'fault',
    customer_phone: '158****0013',
    contact_name: null,
    contact_phone: null,
    created_at: '2026-08-03T03:00:00Z',
  },
  {
    id: 18,
    conversation_id: 7,
    ticket_type: 'transaction',
    status: 'effective',
    content: '办理 20G 流量加装包',
    skill_group: 'plan',
    customer_phone: '138****0001',
    contact_name: null,
    contact_phone: null,
    created_at: '2026-08-03T03:10:00Z',
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

/* ============ 详情 mock 数据源（#23 UI-A-6；TODO backend #44/#45：落地后改真实 fetch） ============ */

/** 各类型状态机主线（不含分支终态 closed/effective；cancelled/failed 由非终态跳入）。 */
const TICKETING_MAIN = ['pending', 'dispatched', 'in_progress', 'awaiting_confirmation']
const TRANSACTION_MAIN = ['pending', 'processing']

function mainSequenceFor(t: Pick<AgentTicket, 'ticket_type'>): string[] {
  return t.ticket_type === 'ticketing' ? TICKETING_MAIN : TRANSACTION_MAIN
}

/**
 * 生成状态流转时间线（PRD §ticket-detail 时间线段）：主线序列到当前态，
 * 分支终态（cancelled/failed/closed/effective）追加于主线末；当前态 is_current 标记。
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

/**
 * 拉取坐席工单详情（US-28：基本信息 + 状态时间线 + 审计日志）。
 * #44/#45 落地后：GET /api/agents/tickets/{id}（坐席 Bearer，含 timeline/audit_logs）。
 */
export async function getAgentTicketDetail(
  ticketId: number,
  _token: string,
): Promise<AgentTicketDetail> {
  const current = _mockTickets.find((t) => t.id === ticketId)
  if (!current) throw new Error('工单不存在')
  return {
    ...current,
    creator: current.customer_phone ?? '访客',
    timeline: buildTimeline(current),
    audit_logs: buildAuditLogs(current),
  }
}

/**
 * 派单到技能组（详情页操作区 US-24）：待派单（工单类 pending）→ 已派单 + 记录技能组。
 * #44/#45 落地后：POST /api/agents/tickets/{id}/dispatch（技能组参数，坐席 Bearer）。
 */
export async function dispatchTicketToGroup(
  ticketId: number,
  skillGroup: string,
  _token: string,
): Promise<AgentTicket> {
  const current = _mockTickets.find((t) => t.id === ticketId)
  if (!current) throw new Error('工单不存在')
  return replaceMock({ ...current, status: 'dispatched', skill_group: skillGroup })
}

/**
 * 取消工单（详情页操作区 US-24）：非终态 → 已取消（状态机允许从非终态进入 cancelled）。
 * #44/#45 落地后：POST /api/agents/tickets/{id}/cancel（坐席 Bearer）。
 */
export async function cancelTicket(ticketId: number, _token: string): Promise<AgentTicket> {
  const current = _mockTickets.find((t) => t.id === ticketId)
  if (!current) throw new Error('工单不存在')
  return replaceMock({ ...current, status: 'cancelled' })
}
