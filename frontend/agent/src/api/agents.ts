/**
 * agent-console API 客户端（REST）。
 *
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（前端一律 `/api/...` → nginx → 后端）。
 * B9 契约：POST /agents/login `{employee_id, password}` →
 *   200 `{access_token, refresh_token, token_type}` | 401 `{detail: "工号或密码错误"}`。
 */

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

/** 登录失败（后端 401，文案同 PRD login 错误变体）。 */
export class AgentLoginError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AgentLoginError'
  }
}

/**
 * 坐席登录（US-19）。
 * 失败抛 AgentLoginError；网络/非 401 错误同样收敛为默认文案，UI 统一走错误态。
 */
export async function agentLogin(employeeId: string, password: string): Promise<TokenResponse> {
  const response = await fetch('/api/agents/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ employee_id: employeeId, password }),
  })

  if (!response.ok) {
    let message = '工号或密码错误'
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') message = body.detail
    } catch {
      // 非 JSON 错误体：沿用默认文案
    }
    throw new AgentLoginError(message)
  }

  return (await response.json()) as TokenResponse
}
