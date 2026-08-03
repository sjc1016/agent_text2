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

/**
 * 凭证失效事件名（issue #58 验收标准 4）：API 层检测到坐席凭证无效/过期（后端 401）时
 * 派发，由路由守卫侧监听统一清除凭证并跳回登录页 —— 与未登录拦截复用同一跳转逻辑。
 */
export const AUTH_EXPIRED_EVENT = 'agent:auth-expired'

/** 派发凭证失效事件（window 同步事件，监听侧即刻处理）。 */
export function dispatchAuthExpired(): void {
  window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
}

/**
 * 坐席凭证 401 判定：后端 auth dependency（get_current_agent）凭证校验失败返回 401 且
 * 携带 `WWW-Authenticate: Bearer`，区别于业务 401（办理执行服务密码失败 / 登录失败）。
 */
export function isAgentCredentialExpired(response: Response): boolean {
  if (response.status !== 401) return false
  return (response.headers.get('WWW-Authenticate') ?? '').toLowerCase().includes('bearer')
}

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

    /**
     * 登出（US-19）：清除坐席凭证回未登录态并清理 localStorage。
     * 顶栏「登出」按钮（#60）与凭证失效 401 引导（#58 守卫监听）共用此 action。
     */
    logout() {
      this.accessToken = ''
      this.refreshToken = ''
      this.employeeId = ''
      localStorage.removeItem(AUTH_STORAGE_KEY)
    },
  },
})
