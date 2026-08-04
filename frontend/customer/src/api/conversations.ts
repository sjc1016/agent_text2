/**
 * customer-web conversations REST 客户端（B1/B2 契约，#24 UI-C-3）。
 *
 * 后端契约（backend/app/conversation/routes.py + schemas.py）：
 *   POST /api/conversations（Bearer）→ 201 ConversationOut {id, customer_id, status, created_at}
 *   GET  /api/conversations/{id}/messages（Bearer）→ 200 list[MessageOut]
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（同 auth.ts，前端一律 /api/...）。
 *
 * 鉴权统一走 api/http.ts（issue #65）：401 + WWW-Authenticate → 自动刷新 access token 重试。
 */

import { authedJson } from './http'

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

/** 拉取当前客户会话列表（B2；#11 profile 会话历史经此 + 每会话消息聚合）。 */
export async function listConversations(token: string): Promise<Conversation[]> {
  return authedJson<Conversation[]>(token, '/api/conversations')
}

/** 创建新会话（认证客户；新会话以 authenticated 起步，#24 对话页入口）。 */
export async function createConversation(token: string): Promise<Conversation> {
  return authedJson<Conversation>(token, '/api/conversations', { method: 'POST' })
}

/** 拉取会话消息历史（按 created_at 升序；会话不存在或非本人 → 404 抛错）。 */
export async function listMessages(token: string, conversationId: number): Promise<ChatMessage[]> {
  return authedJson<ChatMessage[]>(token, `/api/conversations/${conversationId}/messages`)
}
