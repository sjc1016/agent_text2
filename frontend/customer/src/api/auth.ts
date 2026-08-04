/**
 * customer-web API 客户端（REST）。
 *
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（前端一律 `/api/...` → nginx → 后端）。
 * B1 契约：POST /auth/login `{phone, service_password}` →
 *   200 `{access_token, refresh_token, token_type}` | 401 `{detail: "手机号或服务密码错误"}`。
 * 受保护请求（reauth）统一走 api/http.ts（issue #65）：401 + WWW-Authenticate →
 *   自动刷新 access token 重试；业务 401（服务密码错误，无 WWW-Authenticate）原样抛错。
 */

import { authedJson } from './http'

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

/** 办理执行复核响应（backend ReauthResponse：短期 execute_token）。 */
export interface ReauthResponse {
  execute_token: string
  token_type: string
}

/**
 * 办理执行复核（US-12）：再次校验服务密码 → 颁发短期 execute_token。
 * 补偿控制（CONTEXT › 办理执行复核）：复核通过后才能凭 execute_token 触发办理执行。
 * 失败抛 HttpError（后端 401「服务密码错误」→ 复核 Modal 错误文案）。
 * 走 authedJson：access 过期时自动刷新重试（#65），业务 401（密码错）原样抛错。
 */
export async function reauth(token: string, servicePassword: string): Promise<ReauthResponse> {
  return authedJson<ReauthResponse>(token, '/api/auth/reauth', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ service_password: servicePassword }),
  })
}
