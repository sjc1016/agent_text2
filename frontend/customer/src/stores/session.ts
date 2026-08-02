import { defineStore } from 'pinia'
import type { ConversationState } from 'shared/events'

/**
 * 会话状态徽章变体，对应 DESIGN.md §5.7 状态徽章六变体中的三态。
 * 由会话状态机（PRD line 286）派生，作为顶栏徽章视觉语义。
 */
export type SessionBadgeVariant = 'neutral' | 'primary' | 'info'

/** 顶栏会话标题 + 徽章变体 + 徽章文案映射（PRD app-shell 会话标题/徽章段）。 */
interface SessionHeader {
  title: string
  badgeVariant: SessionBadgeVariant
  badgeLabel: string
}

/** 状态机各态 → 顶栏标题/徽章映射（States 矩阵 session-state-variants）。 */
function resolveHeader(state: ConversationState, maskedPhone: string): SessionHeader {
  switch (state) {
    case 'unauthenticated':
      return { title: '在线咨询', badgeVariant: 'neutral', badgeLabel: '访客' }
    case 'authenticated':
    case 'in_progress':
      // 已认证 / 办理中：同为已认证客户，标题展示号码脱敏，徽章 Primary。
      return {
        title: maskedPhone || '已认证',
        badgeVariant: 'primary',
        badgeLabel: '已认证',
      }
    case 'handed_off':
      return {
        title: '坐席服务中',
        badgeVariant: 'info',
        badgeLabel: '转接中',
      }
    case 'closed':
      return { title: '在线咨询', badgeVariant: 'neutral', badgeLabel: '访客' }
  }
}

/**
 * 会话 store：承载会话状态机当前态与号码脱敏，驱动顶栏会话标题/徽章。
 *
 * 状态来源（后续切片接入）：
 *   - conversationState 由 WS `conversation.state` 事件驱动（B2 已定义事件契约）。
 *   - maskedPhone 由认证成功后 REST `/auth/login` 响应写入。
 * app-shell 仅消费其派生视图，不关心写入来源。
 */
export const useSessionStore = defineStore('session', {
  state: () => ({
    conversationState: 'unauthenticated' as ConversationState,
    maskedPhone: '' as string,
  }),
  getters: {
    header(state): SessionHeader {
      return resolveHeader(state.conversationState, state.maskedPhone)
    },
  },
})
