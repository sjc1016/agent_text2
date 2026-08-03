import { defineStore } from 'pinia'

/**
 * 坐席认证 store（agent-console）。
 *
 * 职责：承载坐席 JWT 凭证（B9 /agents/login 响应），供后续坐席 REST/WS 鉴权消费；
 * 持久化 localStorage，刷新后恢复已登录会话（与 customer-web session store 凭证部分同模式）。
 */

/** JWT 凭证（access 2h / refresh 7d，PRD 实现决策 › 认证与会话）。 */
export interface AuthTokens {
  accessToken: string
  refreshToken: string
}

/** localStorage 键：坐席认证凭证。 */
const AUTH_STORAGE_KEY = 'agent.auth'

interface PersistedAuth {
  accessToken: string
  refreshToken: string
  employeeId: string
}

function loadAuth(): PersistedAuth {
  const empty: PersistedAuth = { accessToken: '', refreshToken: '', employeeId: '' }
  const raw = localStorage.getItem(AUTH_STORAGE_KEY)
  if (!raw) return empty
  try {
    const parsed = JSON.parse(raw) as Partial<PersistedAuth>
    if (typeof parsed.accessToken !== 'string') return empty
    return {
      accessToken: parsed.accessToken,
      refreshToken: typeof parsed.refreshToken === 'string' ? parsed.refreshToken : '',
      employeeId: typeof parsed.employeeId === 'string' ? parsed.employeeId : '',
    }
  } catch {
    return empty
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => {
    const persisted = loadAuth()
    return {
      accessToken: persisted.accessToken,
      refreshToken: persisted.refreshToken,
      employeeId: persisted.employeeId,
    }
  },
  getters: {
    /** 是否已登录（存在 access token）。 */
    isAuthenticated(): boolean {
      return this.accessToken !== ''
    },
  },
  actions: {
    /**
     * 登录成功：写入坐席 JWT 凭证（US-19），并持久化以便刷新恢复。
     * 后续坐席 REST/WS 鉴权从此处取 accessToken（#20~#23 消费）。
     */
    setAuthenticated(tokens: AuthTokens, employeeId: string) {
      this.accessToken = tokens.accessToken
      this.refreshToken = tokens.refreshToken
      this.employeeId = employeeId
      localStorage.setItem(
        AUTH_STORAGE_KEY,
        JSON.stringify({
          accessToken: this.accessToken,
          refreshToken: this.refreshToken,
          employeeId: this.employeeId,
        }),
      )
    },
  },
})
