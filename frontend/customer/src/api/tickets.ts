/**
 * customer-web tickets REST 客户端（B7 契约，#16 UI-C-4；B13 补齐通知端点）。
 *
 * 后端契约（backend/app/ticket/routes.py + schemas.py）：
 *   GET /api/tickets（Bearer）→ 200 list[TicketOut]（当前客户工单列表）
 * 后端契约（backend/app/customers/routes.py，B13 #53）：
 *   GET /api/notifications（Bearer）→ 200 list[NotificationOut]（当前客户通知，时间倒序）
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（同 conversations.ts）。
 */

/** 工单（镜像 backend TicketOut）。 */
export interface Ticket {
  id: number
  conversation_id: number
  ticket_type: string
  status: string
  content: string
  customer_id: number | null
  contact_name: string | null
  contact_phone: string | null
  creator_type: string
  creator_id: number | null
  created_at: string
}

/** 站内通知（镜像 backend NotificationPushPayload；read 未读态驱动预览条）。 */
export interface TicketNotification {
  id: number
  ticket_id: number
  message: string
  read: boolean
  created_at: string
}

/** 工单类型 → 展示文案（PRD 页面清单 §tickets 列表段「工单类型图标区分办理类/工单类」）。 */
export function ticketTypeLabel(ticketType: string): string {
  const map: Record<string, string> = {
    transaction: '办理类',
    ticketing: '工单类',
  }
  return map[ticketType] ?? ticketType
}

/** 工单状态 → 展示文案（按类型路由，两状态机并集，PRD line 288-292）。 */
export function ticketStatusLabel(ticket: Ticket): string {
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
 * 工单状态 → 徽章变体（DESIGN.md §5.7 变体；验收标准：Ticket 状态机映射）。
 * 待执行/待派单→Warning、执行中/处理中→Info、已生效/已关闭→Success、
 * 已失败→Error、已取消→Neutral；未列入的状态回退 Neutral。
 */
export function ticketBadgeVariant(
  ticket: Ticket,
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

/** Bearer 请求头（REST 用 Authorization header——PRD 实现决策 › 认证与会话）。 */
function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

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

/** 拉取当前客户工单列表（US-14；未认证 401 由后端守卫）。 */
export async function listTickets(token: string): Promise<Ticket[]> {
  const response = await expectOk(await fetch('/api/tickets', { headers: authHeaders(token) }))
  return (await response.json()) as Ticket[]
}

/** 拉取当前客户站内通知列表（US-14 通知预览条数据源，后端按时间倒序）。 */
export async function listUnreadNotifications(token: string): Promise<TicketNotification[]> {
  const response = await expectOk(
    await fetch('/api/notifications', { headers: authHeaders(token) }),
  )
  return (await response.json()) as TicketNotification[]
}
