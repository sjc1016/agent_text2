import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { createConversation, listMessages } from '../api/conversations'

/**
 * #24 UI-C-3 循环：conversations REST 客户端（B1/B2 契约）。
 *
 * 后端契约（backend/app/conversation/routes.py）：
 *   POST /api/conversations（Bearer）→ 201 ConversationOut {id, customer_id, status, created_at}
 *   GET  /api/conversations/{id}/messages（Bearer）→ 200 list[MessageOut]
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（同 auth.ts）。
 */
const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockClear()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('createConversation（#24）', () => {
  it('携带 Bearer accessToken POST /api/conversations，返回会话', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 7,
        customer_id: 9,
        status: 'authenticated',
        created_at: '2026-08-03T00:00:00Z',
      }),
    })

    const conv = await createConversation('at')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/conversations')
    expect(init.method).toBe('POST')
    expect(init.headers).toEqual({ Authorization: 'Bearer at' })
    expect(conv).toEqual({
      id: 7,
      customer_id: 9,
      status: 'authenticated',
      created_at: '2026-08-03T00:00:00Z',
    })
  })

  it('未认证（401）抛错，不吞失败', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: '未认证' }),
    })

    await expect(createConversation('expired')).rejects.toThrow()
  })
})

describe('listMessages（#24）', () => {
  it('GET /api/conversations/{id}/messages 返回消息历史（升序）', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => [
        {
          id: 1,
          conversation_id: 7,
          source: 'assistant',
          content: '您好',
          created_at: '2026-08-03T00:00:01Z',
        },
        {
          id: 2,
          conversation_id: 7,
          source: 'user',
          content: '查话费',
          created_at: '2026-08-03T00:00:02Z',
        },
      ],
    })

    const messages = await listMessages('at', 7)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/conversations/7/messages')
    expect(init.headers).toEqual({ Authorization: 'Bearer at' })
    expect(messages).toHaveLength(2)
    expect(messages[0].source).toBe('assistant')
    expect(messages[1].content).toBe('查话费')
  })

  it('会话不存在（404）抛错', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: '会话不存在' }),
    })

    await expect(listMessages('at', 999)).rejects.toThrow()
  })
})
