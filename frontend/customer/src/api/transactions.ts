/**
 * customer-web transactions REST 客户端（#24 UI-C-3 二次确认 / 执行复核）。
 *
 * 后端契约（backend/app/transaction/routes.py + schemas.py；backend/app/auth/routes.py）：
 *   POST /api/transactions/confirm（Bearer access）→ 201 TicketOut
 *     body {conversation_id, content}（办理内容写入 Ticket.content；二次确认入队）
 *   POST /api/transactions/{ticket_id}/execute（Bearer execute_token）→ 200 TicketOut
 *     execute_token 由 POST /api/auth/reauth 复核服务密码后颁发（补偿控制）
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（同 conversations.ts）。
 *
 * 鉴权统一走 api/http.ts（issue #65）：401 + WWW-Authenticate → 自动刷新 access token 重试。
 * 注意：execute_token 为短期凭证、无 refresh 路径，execute 请求 optOut401（业务 401 非凭证过期）。
 */

import { authedJson } from './http'

/** 工单（镜像 backend TicketOut 中前端消费的字段）。 */
export interface Ticket {
  id: number
  conversation_id: number
  ticket_type: string
  status: string
  content: string
}

/** 二次确认（US-8~US-11）：用户确认办理 → 创建办理类 Ticket(Pending) 入队。 */
export async function confirmTransaction(
  token: string,
  conversationId: number,
  content: string,
): Promise<Ticket> {
  return authedJson<Ticket>(token, '/api/transactions/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId, content }),
  })
}

/** 执行办理（US-12）：凭 execute_token 触发 pending → processing → effective。 */
export async function executeTicket(executeToken: string, ticketId: number): Promise<Ticket> {
  return authedJson<Ticket>(
    executeToken,
    `/api/transactions/${ticketId}/execute`,
    { method: 'POST' },
    { optOut401: true },
  )
}
