/**
 * customer-web transactions REST 客户端（#24 UI-C-3 二次确认 / 执行复核）。
 *
 * 后端契约（backend/app/transaction/routes.py + schemas.py；backend/app/auth/routes.py）：
 *   POST /api/transactions/confirm（Bearer access）→ 201 TicketOut
 *     body {conversation_id, content}（办理内容写入 Ticket.content；二次确认入队）
 *   POST /api/transactions/{ticket_id}/execute（Bearer execute_token）→ 200 TicketOut
 *     execute_token 由 POST /api/auth/reauth 复核服务密码后颁发（补偿控制）
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（同 conversations.ts）。
 */

/** 工单（镜像 backend TicketOut 中前端消费的字段）。 */
export interface Ticket {
  id: number
  conversation_id: number
  ticket_type: string
  status: string
  content: string
}

/** Bearer 请求头（REST 用 Authorization header，WS 用 JWT 查询参数——PRD 实现决策）。 */
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

/** 二次确认（US-8~US-11）：用户确认办理 → 创建办理类 Ticket(Pending) 入队。 */
export async function confirmTransaction(
  token: string,
  conversationId: number,
  content: string,
): Promise<Ticket> {
  const response = await expectOk(
    await fetch('/api/transactions/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders(token) },
      body: JSON.stringify({ conversation_id: conversationId, content }),
    }),
  )
  return (await response.json()) as Ticket
}

/** 执行办理（US-12）：凭 execute_token 触发 pending → processing → effective。 */
export async function executeTicket(executeToken: string, ticketId: number): Promise<Ticket> {
  const response = await expectOk(
    await fetch(`/api/transactions/${ticketId}/execute`, {
      method: 'POST',
      headers: authHeaders(executeToken),
    }),
  )
  return (await response.json()) as Ticket
}
