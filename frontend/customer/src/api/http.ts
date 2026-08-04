/**
 * customer-web 共享 HTTP 基础设施（issue #65）：统一鉴权请求 + 401 凭证刷新。
 *
 * 背景（#65）：access token（2h）过期后，仅判断 token 存在导致「假已认证态」，
 * 受保护请求 401 被静默吞掉、消息不发不显。本模块提供：
 *   - `fetchAuthed`：普通 Bearer 请求（无刷新路径的凭证，如 execute_token）。
 *   - `fetchAuthedWithRefresh`：Bearer 请求 + 401（带 WWW-Authenticate）自动
 *     刷新 access token 并重试一次（单飞，避免并发刷新风暴）。
 *   - `refreshSessionAccessToken`：单飞刷新；refresh token 也失效 → session.logout()。
 *
 * 凭证 401 判定与 agent-console 一致（#58）：后端 auth dependency 校验失败返回
 * 401 且携带 `WWW-Authenticate: Bearer`，区别于业务 401（服务密码错误等，不携带）。
 *
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（前端一律 /api/...）。
 */

import { useSessionStore } from '../stores/session'

/** 业务错误（携带 HTTP status，供视图区分 401 等错误态）。 */
export class HttpError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'HttpError'
    this.status = status
  }
}

/** 凭证 401 判定：后端 auth dependency 401 携带 WWW-Authenticate: Bearer（同 agent 侧 #58）。 */
export function isCredentialExpired(response: Response): boolean {
  if (response.status !== 401) return false
  const headers = response.headers as Headers | undefined
  return (headers?.get('WWW-Authenticate') ?? '').toLowerCase().includes('bearer')
}

/** Bearer 请求头（REST 用 Authorization header——PRD 实现决策 › 认证与会话）。 */
export function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

/** 解析错误体 detail；非 JSON / 无 detail 沿用默认文案。 */
async function errorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string' && body.detail) return body.detail
  } catch {
    // 非 JSON 错误体：沿用默认文案
  }
  return fallback
}

/** 非 2xx → 抛 HttpError(status, detail)；成功原样返回。 */
async function expectOk(response: Response): Promise<Response> {
  if (!response.ok) {
    const fallback = '请求失败'
    throw new HttpError(await errorDetail(response, fallback), response.status)
  }
  return response
}

/** 校验通过后解析 JSON（供 API 函数复用）。 */
async function parseJson<T>(response: Response): Promise<T> {
  return (await expectOk(response).then((r) => r.json())) as T
}

/** 合并 Bearer 头到已有 init（不覆盖调用方传入的 Content-Type 等）。 */
function withAuthHeaders(token: string, init?: RequestInit): RequestInit {
  return { ...init, headers: { ...authHeaders(token), ...(init?.headers ?? {}) } }
}

/** 普通鉴权请求（不做 401 刷新拦截：execute_token 等无 refresh 路径的凭证）。 */
export async function fetchAuthed(
  token: string,
  url: string,
  init?: RequestInit,
): Promise<Response> {
  return fetch(url, withAuthHeaders(token, init))
}

/**
 * 带凭证自动刷新的鉴权请求（issue #65）：
 * 首次 401 且带 WWW-Authenticate（access 凭证过期）→ 刷新 access token 后重试一次；
 * 重试仍 401 / 非凭证 401（业务错误）→ 原样返回（由 expectOk 抛错）。
 */
export async function fetchAuthedWithRefresh(
  token: string,
  url: string,
  init?: RequestInit,
): Promise<Response> {
  let response = await fetchAuthed(token, url, init)
  if (!response.ok && isCredentialExpired(response)) {
    const fresh = await refreshSessionAccessToken()
    response = await fetchAuthed(fresh, url, init)
  }
  return response
}

/** 鉴权请求 + 校验 + JSON 解析（刷新拦截默认开启；optOut401 用于 execute_token 路径）。 */
export async function authedJson<T>(
  token: string,
  url: string,
  init?: RequestInit,
  opts?: { optOut401?: boolean },
): Promise<T> {
  const doFetch = opts?.optOut401 ? fetchAuthed : fetchAuthedWithRefresh
  const response = await doFetch(token, url, init)
  return parseJson<T>(response)
}

/**
 * POST /api/auth/refresh：用 refresh token 换发新 access token（#65，后端 /auth/refresh）。
 * 失败抛 HttpError（401 = refresh 凭证失效，调用方应 logout）。
 */
export async function refreshAccessToken(refreshToken: string): Promise<{ access_token: string }> {
  const response = await fetch('/api/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  return parseJson<{ access_token: string }>(response)
}

/** 单飞刷新 promise：并发 401 只触发一次 /auth/refresh（避免刷新风暴）。 */
let refreshInFlight: Promise<string> | null = null

/**
 * 单飞刷新 access token 并写回 session store：
 *   - 成功 → 返回新 access token（后续请求读 store 拿新 token）；
 *   - refresh token 缺失 / refresh 请求失败 → session.logout()（回访客态，视图转认证引导）。
 */
export function refreshSessionAccessToken(): Promise<string> {
  if (refreshInFlight) return refreshInFlight
  refreshInFlight = (async () => {
    const session = useSessionStore()
    const refreshToken = session.refreshToken
    if (!refreshToken) {
      session.logout()
      throw new HttpError('登录已过期，请重新登录', 401)
    }
    try {
      const { access_token } = await refreshAccessToken(refreshToken)
      session.setAccessToken(access_token)
      return access_token
    } catch (err) {
      session.logout()
      if (err instanceof HttpError) throw err
      throw new HttpError('登录已过期，请重新登录', 401)
    }
  })().finally(() => {
    refreshInFlight = null
  })
  return refreshInFlight
}
