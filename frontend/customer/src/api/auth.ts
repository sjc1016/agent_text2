/**
 * customer-web API 客户端（REST）。
 *
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（前端一律 `/api/...` → nginx → 后端）。
 * B1 契约：POST /auth/login `{phone, service_password}` →
 *   200 `{access_token, refresh_token, token_type}` | 401 `{detail: "手机号或服务密码错误"}`。
 */

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

/** 认证失败（后端 401，文案同 PRD auth 错误变体）。 */
export class AuthError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AuthError'
  }
}

/**
 * 服务密码登录（US-2）。
 * 失败抛 AuthError；网络/非 401 错误同样收敛为 AuthError 文案，UI 统一走错误态。
 */
export async function login(phone: string, servicePassword: string): Promise<LoginResponse> {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phone, service_password: servicePassword }),
  })

  if (!response.ok) {
    let message = '手机号或服务密码错误'
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') message = body.detail
    } catch {
      // 非 JSON 错误体：沿用默认文案
    }
    throw new AuthError(message)
  }

  return (await response.json()) as LoginResponse
}
