import { defineStore } from 'pinia'
import type { ConversationState } from 'shared/events'

/**
 * 会话状态徽章变体，对应 DESIGN.md §5.7 状态徽章六变体中的三态。
 * 由会话状态机（PRD line 286）派生，作为顶栏徽章视觉语义。
 */
export type SessionBadgeVariant = 'neutral' | 'primary' | 'info'

/** JWT 凭证（access 2h / refresh 7d，PRD 实现决策 › 认证与会话）。 */
export interface AuthTokens {
  accessToken: string
  refreshToken: string
}

/** localStorage 键：认证凭证 + 号码脱敏（刷新后恢复已认证会话）。 */
const AUTH_STORAGE_KEY = 'customer.auth'

/** 号码脱敏：138****0001（与 backend/app/agents/service.py mask_phone 同规格）。 */
export function maskPhone(phone: string): string {
  return phone.length >= 7 ? `${phone.slice(0, 3)}****${phone.slice(-4)}` : phone
}

interface PersistedAuth {
  accessToken: string
  refreshToken: string
  maskedPhone: string
}

function loadAuth(): PersistedAuth {
  const empty: PersistedAuth = { accessToken: '', refreshToken: '', maskedPhone: '' }
  const raw = localStorage.getItem(AUTH_STORAGE_KEY)
  if (!raw) return empty
  try {
    const parsed = JSON.parse(raw) as Partial<PersistedAuth>
    if (typeof parsed.accessToken !== 'string') return empty
    return {
      accessToken: parsed.accessToken,
      refreshToken: typeof parsed.refreshToken === 'string' ? parsed.refreshToken : '',
      maskedPhone: typeof parsed.maskedPhone === 'string' ? parsed.maskedPhone : '',
    }
  } catch {
    return empty
  }
}

/** 顶栏会话标题 + 徽章变体 + 徽章文案映射（PRD app-shell 会话标题/徽章段）。 */
interface SessionHeader {
  title: string
  badgeVariant: SessionBadgeVariant
  badgeLabel: string
}

/** 状态机各态 → 顶栏标题/徽章映射（States 矩阵 session-state-variants）。 */
function resolveHeader(state: ConversationState, maskedPhone: string): SessionHeader {
  switch (state) {
    case 'unauthenticated':
      return { title: '在线咨询', badgeVariant: 'neutral', badgeLabel: '访客' }
    case 'authenticated':
    case 'in_progress':
      // 已认证 / 办理中：同为已认证客户，标题展示号码脱敏，徽章 Primary。
      return {
        title: maskedPhone || '已认证',
        badgeVariant: 'primary',
        badgeLabel: '已认证',
      }
    case 'handed_off':
      return {
        title: '坐席服务中',
        badgeVariant: 'info',
        badgeLabel: '转接中',
      }
    case 'closed':
      return { title: '在线咨询', badgeVariant: 'neutral', badgeLabel: '访客' }
  }
}

/**
 * 会话 store：承载会话状态机当前态、号码脱敏与 JWT 凭证，驱动顶栏会话标题/徽章。
 *
 * 状态来源：
 *   - conversationState 由 WS `conversation.state` 事件驱动（B2 已定义事件契约）；
 *     /auth 认证成功（US-2）本地置为 `authenticated`，刷新后经 localStorage 恢复。
 *   - maskedPhone 由认证成功后 REST `/auth/login` 响应写入（号码脱敏）。
 *   - accessToken/refreshToken 供后续 REST/WS 鉴权使用，持久化 localStorage。
 * app-shell 仅消费其派生视图，不关心写入来源。
 */
export const useSessionStore = defineStore('session', {
  state: () => {
    const persisted = loadAuth()
    return {
      conversationState: (persisted.accessToken
        ? 'authenticated'
        : 'unauthenticated') as ConversationState,
      maskedPhone: persisted.maskedPhone,
      accessToken: persisted.accessToken,
      refreshToken: persisted.refreshToken,
    }
  },
  getters: {
    header(state): SessionHeader {
      return resolveHeader(state.conversationState, state.maskedPhone)
    },
    /**
     * 是否已认证（存在 access 或 refresh token，issue #65）。
     * access token 过期但 refresh token 仍有效 → 仍视为已认证（可经 401 拦截自动刷新），
     * 避免「假已认证态」下请求 401 被吞掉；两者皆无 → 访客态。
     */
    isAuthenticated(): boolean {
      return this.accessToken !== '' || this.refreshToken !== ''
    },
  },
  actions: {
    /**
     * 认证成功：写入 JWT 凭证 + 升格客户（US-2），并持久化以便刷新恢复。
     * 顶栏随即展示号码脱敏 + Primary 徽章「已认证」（resolveHeader）。
     */
    setAuthenticated(tokens: AuthTokens, phone: string) {
      this.accessToken = tokens.accessToken
      this.refreshToken = tokens.refreshToken
      this.maskedPhone = maskPhone(phone)
      this.conversationState = 'authenticated'
      localStorage.setItem(
        AUTH_STORAGE_KEY,
        JSON.stringify({ ...tokens, maskedPhone: this.maskedPhone }),
      )
    },

    /**
     * 刷新后写回新 access token（issue #65）：内存 + localStorage 同步，
     * 后续 REST/WS 从 store 读取新 token。
     */
    setAccessToken(token: string) {
      this.accessToken = token
      const raw = localStorage.getItem(AUTH_STORAGE_KEY)
      if (raw) {
        try {
          const parsed = JSON.parse(raw) as Partial<PersistedAuth>
          localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify({ ...parsed, accessToken: token }))
        } catch {
          // 解析失败不覆盖存储
        }
      }
    },

    /**
     * 消费 WS `conversation.state` 事件写入状态机当前态（#24 UI-C-3）。
     * 仅状态流转，不触碰 JWT 凭证；顶栏标题/徽章随 resolveHeader 派生变化。
     */
    setConversationState(state: ConversationState) {
      this.conversationState = state
    },

    /**
     * 退出登录（US-17）：清除 JWT 凭证与号码脱敏，状态回访客（unauthenticated）。
     * 顶栏随即回「在线咨询 + 访客徽章」；对话流数据（chat store）由视图层一并 reset。
     */
    logout() {
      this.accessToken = ''
      this.refreshToken = ''
      this.maskedPhone = ''
      this.conversationState = 'unauthenticated'
      localStorage.removeItem(AUTH_STORAGE_KEY)
    },
  },
})
