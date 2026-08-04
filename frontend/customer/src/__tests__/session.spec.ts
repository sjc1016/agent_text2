import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useSessionStore } from '../stores/session'
import type { ConversationState } from 'shared/events'

/**
 * #24 UI-C-3 循环：session store 消费 WS `conversation.state` 事件。
 *
 * 状态来源契约（stores/session.ts 注释）：conversationState 由 WS
 * `conversation.state` 事件驱动，驱动顶栏会话标题/徽章（resolveHeader）。
 * 本循环新增 `setConversationState` action 供 chat WS 客户端写入。
 */
describe('session store — setConversationState（#24）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('写入新状态后顶栏派生视图同步变化（handed_off → 转接中徽章）', () => {
    const store = useSessionStore()
    expect(store.header.badgeLabel).toBe('访客')

    store.setConversationState('handed_off')

    expect(store.conversationState).toBe('handed_off')
    expect(store.header.badgeVariant).toBe('info')
    expect(store.header.badgeLabel).toBe('转接中')
    expect(store.header.title).toBe('坐席服务中')
  })

  it('已认证会话回退 in_progress 保持已认证展示', () => {
    const store = useSessionStore()
    store.setAuthenticated({ accessToken: 'at', refreshToken: 'rt' }, '13800001234')
    store.setConversationState('in_progress')

    expect(store.header.badgeLabel).toBe('已认证')
    expect(store.header.badgeVariant).toBe('primary')
  })

  it('不篡改 JWT 凭证（仅状态流转）', () => {
    const store = useSessionStore()
    store.setAuthenticated({ accessToken: 'at', refreshToken: 'rt' }, '13800001234')
    store.setConversationState('handed_off')

    expect(store.accessToken).toBe('at')
    expect(store.maskedPhone).toBe('138****1234')
  })

  it('setConversationState 仅接受合法状态机状态（类型收窄编译期验证）', () => {
    const store = useSessionStore()
    const states: ConversationState[] = [
      'unauthenticated',
      'authenticated',
      'in_progress',
      'handed_off',
      'closed',
    ]
    for (const s of states) {
      store.setConversationState(s)
      expect(store.conversationState).toBe(s)
    }
  })
})

describe('session store — 401 刷新（issue #65）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('setAccessToken：内存 + localStorage 同步写回新 token（刷新后 REST/WS 取新值）', () => {
    const store = useSessionStore()
    store.setAuthenticated({ accessToken: 'at', refreshToken: 'rt' }, '13800001234')
    const before = JSON.parse(localStorage.getItem('customer.auth') ?? '{}')
    expect(before.accessToken).toBe('at')

    store.setAccessToken('fresh')

    expect(store.accessToken).toBe('fresh')
    expect(store.refreshToken).toBe('rt') // refresh token 不受影响
    const persisted = JSON.parse(localStorage.getItem('customer.auth') ?? '{}')
    expect(persisted.accessToken).toBe('fresh')
    expect(persisted.refreshToken).toBe('rt')
    expect(persisted.maskedPhone).toBe('138****1234') // 其余字段不覆盖
  })

  it('isAuthenticated：access 过期但 refresh 仍有效 → 仍视为已认证（可自动刷新）', () => {
    const store = useSessionStore()
    // 模拟 access 过期：仅剩 refresh token（#65 假已认证态根因）
    store.accessToken = ''
    store.refreshToken = 'rt'

    expect(store.isAuthenticated).toBe(true)

    store.refreshToken = ''
    expect(store.isAuthenticated).toBe(false)
  })

  it('setAuthenticated 写入双 token 后 isAuthenticated 为 true', () => {
    const store = useSessionStore()
    store.setAuthenticated({ accessToken: 'at', refreshToken: 'rt' }, '13800001234')
    expect(store.isAuthenticated).toBe(true)
  })
})
