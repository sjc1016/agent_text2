import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { authedJson, HttpError, isCredentialExpired, refreshSessionAccessToken } from '../api/http'
import { useSessionStore } from '../stores/session'

/**
 * #65 循环：customer-web 共享 HTTP 基础设施（401 拦截 + refresh token 单飞刷新）。
 *
 * 行为契约（api/http.ts）：
 *   - fetchAuthedWithRefresh：401 + WWW-Authenticate（凭证过期）→ POST /api/auth/refresh
 *     换发新 access token 并重试一次；业务 401（无 WWW-Authenticate）不刷新原样抛错。
 *   - refreshSessionAccessToken：单飞（并发 401 只刷新一次）；refresh 缺失/失败 →
 *     session.logout()（回访客态）。
 *   - execute_token 等无 refresh 路径凭证走 optOut401（fetchAuthed，不拦截）。
 */

const fetchMock = vi.fn()

/** 构造凭证过期响应（401 + WWW-Authenticate: Bearer，与后端 auth dependency 一致）。 */
function credentialExpired(detail = '未认证'): Response {
  return new Response(JSON.stringify({ detail }), {
    status: 401,
    headers: { 'WWW-Authenticate': 'Bearer' },
  })
}

function okJson(data: unknown): Response {
  return new Response(JSON.stringify(data), { status: 200 })
}

function businessError(status: number, detail: string): Response {
  return new Response(JSON.stringify({ detail }), { status })
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

/** 已登录会话（access 'at' + refresh 'rt'，持久化）。 */
function makeAuthenticated() {
  const session = useSessionStore()
  session.setAuthenticated({ accessToken: 'at', refreshToken: 'rt' }, '13800001234')
  return session
}

describe('isCredentialExpired（#65）', () => {
  it('401 + WWW-Authenticate: Bearer → 凭证过期', () => {
    expect(isCredentialExpired(credentialExpired())).toBe(true)
  })

  it('401 无 WWW-Authenticate（业务错误）→ 非凭证过期', () => {
    expect(isCredentialExpired(businessError(401, '服务密码错误'))).toBe(false)
  })

  it('非 401 → 非凭证过期', () => {
    expect(isCredentialExpired(businessError(500, '服务器错误'))).toBe(false)
  })
})

describe('authedJson 401 自动刷新（#65）', () => {
  it('access 过期：POST /auth/refresh 换新 token → 重试原请求成功，无需重新登录', async () => {
    makeAuthenticated()
    fetchMock
      .mockResolvedValueOnce(credentialExpired()) // 首次 401
      .mockResolvedValueOnce(okJson({ access_token: 'fresh' })) // /auth/refresh
      .mockResolvedValueOnce(okJson({ id: 7 })) // 重试成功

    const data = await authedJson<{ id: number }>('at', '/api/conversations', {
      method: 'POST',
    })

    expect(data).toEqual({ id: 7 })

    // 刷新写回 store：后续请求（REST/WS）自动使用新 token
    expect(useSessionStore().accessToken).toBe('fresh')
    expect(useSessionStore().refreshToken).toBe('rt') // refresh token 不变
    expect(useSessionStore().isAuthenticated).toBe(true)

    // 调用序列：原请求 → refresh → 重试（Authorization 用新 token）
    expect(fetchMock.mock.calls[0][0]).toBe('/api/conversations')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/auth/refresh')
    expect(JSON.parse(String(fetchMock.mock.calls[1][1].body))).toEqual({
      refresh_token: 'rt',
    })
    const retryInit = fetchMock.mock.calls[2][1] as RequestInit
    expect((retryInit.headers as Record<string, string>).Authorization).toBe('Bearer fresh')
  })

  it('业务 401（无 WWW-Authenticate）不刷新，原样抛 HttpError（detail 透传）', async () => {
    makeAuthenticated()
    fetchMock.mockResolvedValueOnce(businessError(401, '手机号或服务密码错误'))

    await expect(authedJson('at', '/api/conversations')).rejects.toMatchObject({
      status: 401,
      message: '手机号或服务密码错误',
    })

    expect(fetchMock).toHaveBeenCalledTimes(1) // 未触发 refresh
    expect(useSessionStore().isAuthenticated).toBe(true) // 未登出
  })

  it('并发 401 单飞：仅触发一次 /auth/refresh，两次请求均重试成功', async () => {
    makeAuthenticated()
    // 两个请求并发：各自首次 401 → 共享同一次 refresh → 各自重试成功
    fetchMock
      .mockResolvedValueOnce(credentialExpired())
      .mockResolvedValueOnce(credentialExpired())
      .mockResolvedValueOnce(okJson({ access_token: 'fresh' }))
      .mockResolvedValueOnce(okJson({ a: 1 }))
      .mockResolvedValueOnce(okJson({ b: 2 }))

    const [r1, r2] = await Promise.all([
      authedJson<{ a: number }>('at', '/api/a'),
      authedJson<{ b: number }>('at', '/api/b'),
    ])

    expect(r1).toEqual({ a: 1 })
    expect(r2).toEqual({ b: 2 })
    const refreshCalls = fetchMock.mock.calls.filter(([url]) => url === '/api/auth/refresh')
    expect(refreshCalls).toHaveLength(1)
  })
})

describe('refresh 失败自动登出（#65）', () => {
  it('refresh token 也失效：logout 清凭证（回访客态）并抛错', async () => {
    makeAuthenticated()
    fetchMock
      .mockResolvedValueOnce(credentialExpired()) // 原请求 401
      .mockResolvedValueOnce(businessError(401, '刷新凭证无效或已过期')) // refresh 也 401

    await expect(authedJson('at', '/api/conversations')).rejects.toMatchObject({
      status: 401,
      message: '刷新凭证无效或已过期',
    })

    const session = useSessionStore()
    expect(session.accessToken).toBe('')
    expect(session.refreshToken).toBe('')
    expect(session.isAuthenticated).toBe(false)
    expect(localStorage.getItem('customer.auth')).toBeNull()
  })

  it('refresh token 缺失：直接 logout 并抛错（不会发起 /auth/refresh）', async () => {
    const session = useSessionStore()
    session.setAuthenticated({ accessToken: 'at', refreshToken: 'rt' }, '13800001234')
    session.refreshToken = '' // 模拟 refresh token 丢失（如存储被清）

    await expect(refreshSessionAccessToken()).rejects.toMatchObject({ status: 401 })

    expect(session.isAuthenticated).toBe(false)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('HttpError（#65）', () => {
  it('携带 status 供视图区分错误态（401 登出引导 vs 普通错误）', () => {
    const err = new HttpError('登录已过期，请重新登录', 401)
    expect(err.status).toBe(401)
    expect(err.name).toBe('HttpError')
    expect(err).toBeInstanceOf(Error)
  })
})
