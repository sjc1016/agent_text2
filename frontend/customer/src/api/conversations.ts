/**
 * customer-web conversations REST 客户端（B1/B2 契约，#24 UI-C-3）。
 *
 * 后端契约（backend/app/conversation/routes.py + schemas.py）：
 *   POST /api/conversations（Bearer）→ 201 ConversationOut {id, customer_id, status, created_at}
 *   GET  /api/conversations/{id}/messages（Bearer）→ 200 list[MessageOut]
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（同 auth.ts，前端一律 /api/...）。
 */

/** 会话（镜像 backend ConversationOut）。 */
export interface Conversation {
  id: number
  customer_id: number | null
  status: string
  created_at: string
}

/** 对话流消息（镜像 backend MessageOut；source 四类与 message.new payload 一致）。 */
export interface ChatMessage {
  id: number
  conversation_id: number
  source: 'user' | 'assistant' | 'agent' | 'system'
  content: string
  created_at: string
}

/** Bearer 请求头（WS 用 JWT 查询参数，REST 用 Authorization header——PRD 实现决策）。 */
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

/** 拉取当前客户会话列表（B2；#11 profile 会话历史经此 + 每会话消息聚合）。 */
export async function listConversations(token: string): Promise<Conversation[]> {
  const response = await expectOk(
    await fetch('/api/conversations', { headers: authHeaders(token) }),
  )
  return (await response.json()) as Conversation[]
}

/** 创建新会话（认证客户；新会话以 authenticated 起步，#24 对话页入口）。 */
export async function createConversation(token: string): Promise<Conversation> {
  const response = await expectOk(
    await fetch('/api/conversations', { method: 'POST', headers: authHeaders(token) }),
  )
  return (await response.json()) as Conversation
}

/** 拉取会话消息历史（按 created_at 升序；会话不存在或非本人 → 404 抛错）。 */
export async function listMessages(token: string, conversationId: number): Promise<ChatMessage[]> {
  const response = await expectOk(
    await fetch(`/api/conversations/${conversationId}/messages`, {
      headers: authHeaders(token),
    }),
  )
  return (await response.json()) as ChatMessage[]
}
