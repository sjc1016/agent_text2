import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { listUnreadNotifications } from '../api/tickets'

/**
 * #53 B13 循环：tickets REST 客户端（B13 AC4 替换 MOCK_NOTIFICATIONS）。
 *
 * 后端契约（backend/app/customers/routes.py）：
 *   GET /api/notifications（Bearer）→ 200 list[NotificationOut]（当前客户通知，时间倒序）
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（同 conversations.ts）。
 */
const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockClear()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('listUnreadNotifications（B13）', () => {
  it('携带 Bearer accessToken GET /api/notifications，返回通知列表（含未读标记）', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => [
        {
          id: 2,
          ticket_id: 2,
          message: '您的工单已派单',
          read: false,
          created_at: '2026-08-03T02:30:00Z',
        },
        {
          id: 1,
          ticket_id: 1,
          message: '您的办理工单已生效',
          read: true,
          created_at: '2026-08-03T02:00:00Z',
        },
      ],
    })

    const notifications = await listUnreadNotifications('at')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/notifications')
    expect(init.headers).toEqual({ Authorization: 'Bearer at' })
    expect(notifications).toHaveLength(2)
    expect(notifications[0].message).toBe('您的工单已派单')
    expect(notifications[0].read).toBe(false)
  })

  it('未认证（401）抛错，不吞失败', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: '未认证' }),
    })

    await expect(listUnreadNotifications('expired')).rejects.toThrow()
  })
})
