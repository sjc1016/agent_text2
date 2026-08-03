import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { listQueueItems } from '../api/agents'
import { AUTH_EXPIRED_EVENT } from '../stores/auth'

/**
 * #58 凭证失效 401 判定（验收标准 4）：
 * 后端 auth dependency（get_current_agent）凭证校验失败返回 401 且携带
 * `WWW-Authenticate: Bearer` → API 层派发 auth-expired 事件（守卫监听跳登录）；
 * 业务 401（办理执行服务密码失败等）不携带该头 → 不派发，保持原错误路径。
 */

const fetchMock = vi.fn()

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('api/agents — 坐席凭证 401 派发凭证失效事件', () => {
  it('队列接口 401（WWW-Authenticate: Bearer）→ 派发 auth-expired 事件并抛错', async () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent')
    fetchMock.mockResolvedValue({
      ok: false,
      status: 401,
      headers: new Headers({ 'WWW-Authenticate': 'Bearer' }),
      json: async () => ({ detail: '未提供有效的坐席认证凭据' }),
    })

    await expect(listQueueItems('expired-token')).rejects.toThrow('未提供有效的坐席认证凭据')

    expect(dispatchSpy).toHaveBeenCalledTimes(1)
    const event = dispatchSpy.mock.calls[0][0] as Event
    expect(event.type).toBe(AUTH_EXPIRED_EVENT)
  })

  it('业务 401（无 WWW-Authenticate，如服务密码失败）→ 不派发事件', async () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent')
    fetchMock.mockResolvedValue({
      ok: false,
      status: 401,
      headers: new Headers(),
      json: async () => ({ detail: '执行失败：服务密码错误' }),
    })

    await expect(listQueueItems('token')).rejects.toThrow('执行失败：服务密码错误')
    expect(dispatchSpy).not.toHaveBeenCalled()
  })

  it('非 401 错误（如 500）→ 不派发事件', async () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent')
    fetchMock.mockResolvedValue({
      ok: false,
      status: 500,
      headers: new Headers({ 'WWW-Authenticate': 'Bearer' }),
      json: async () => ({ detail: '服务器错误' }),
    })

    await expect(listQueueItems('token')).rejects.toThrow('服务器错误')
    expect(dispatchSpy).not.toHaveBeenCalled()
  })
})
