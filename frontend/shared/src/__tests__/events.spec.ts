import { describe, it, expect } from 'vitest'

import { WS_EVENT_NAMES, type WsEvent } from '../events'

/**
 * F0 循环5：WS 事件契约 SSOT（前端侧）。
 *
 * 验收标准（issue #2 / PRD 第282行）：
 *   frontend/shared/events.ts 作为 WS 事件名 SSOT，含 PRD 定义的全部事件名，
 *   与 backend/app/ws/events.py 镜像一致（双边一致由后端契约测试校验）。
 *
 * 这里只断言前端 SSOT 自身的正确性：事件名清单完整、顺序固定、无重复。
 */
describe('WS 事件契约 SSOT（frontend/shared/events.ts）', () => {
  it('包含 PRD 第282行定义的全部 11 个事件名，顺序固定', () => {
    expect(WS_EVENT_NAMES).toEqual([
      'llm.token',
      'message.new',
      'handoff.start',
      'handoff.end',
      'ticket.update',
      'notification.push',
      'system.message',
      'agent.status',
      'conversation.state',
      'second.confirm',
      'reauth.required',
    ])
  })

  it('事件名唯一无重复', () => {
    expect(new Set(WS_EVENT_NAMES).size).toBe(WS_EVENT_NAMES.length)
  })
})

/**
 * #24 UI-C-3 循环：细化 'llm.token' payload（镜像 backend/app/ws/events.py LlmTokenPayload）。
 * 之前为 Record<string, unknown> 占位；现应可携带会话定位 + 流式分片 token。
 */
describe('llm.token 事件 payload（#24）', () => {
  it('payload 含 conversation_id + token，可放入 WsEvent envelope 消费', () => {
    const event: WsEvent<'llm.token'> = {
      event: 'llm.token',
      data: { conversation_id: 42, token: '你好' },
    }
    expect(event.data.conversation_id).toBe(42)
    expect(event.data.token).toBe('你好')
  })
})
