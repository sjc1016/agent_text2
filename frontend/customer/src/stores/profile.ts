import { defineStore } from 'pinia'

import { listConversations, listMessages } from '../api/conversations'

/**
 * profile store（#11 UI-C-5）：承载「我的」页数据源与交互态。
 *
 * 职责边界：
 *   - history：会话历史列表（US-17）——经 B2 `GET /conversations` + 每会话
 *     `GET /conversations/{id}/messages` 聚合「起止时间 + 末条消息预览」。
 *   - loading：列表加载态（States 矩阵 loading → 骨架屏）。
 *   - planSummary：当前套餐简述（账号卡片）——后端无 customer-web 账户资料
 *     查询端点，沿用 #16/#20/#21 mock-先行模式，后端落地后替换。
 *   - 认证态不在此判定：视图层按 session.isAuthenticated 路由到访客变体。
 */

/** 会话历史列表项（会话 + 末条消息预览 + 止时间聚合结果）。 */
export interface ConversationHistoryItem {
  id: number
  status: string
  /** 会话创建时间（起）。 */
  startedAt: string
  /** 末条消息时间（止；会话无消息时 null）。 */
  endedAt: string | null
  /** 末条消息内容预览（视图层 CSS 截断）。 */
  preview: string
}

/**
 * 当前套餐简述（账号卡片 Body-sm；数据缺口：后端无端点。
 * TODO(backend)：补 GET /customers/me 账户资料后替换为真实数据源）。
 */
const MOCK_PLAN_SUMMARY = '畅享套餐 59 元/月'

export const useProfileStore = defineStore('profile', {
  state: () => ({
    history: [] as ConversationHistoryItem[],
    loading: false,
  }),
  getters: {
    planSummary(): string {
      return MOCK_PLAN_SUMMARY
    },
  },
  actions: {
    /** 拉取会话历史（并发放置 loading；失败抛出由视图层处理）。 */
    async load(token: string): Promise<void> {
      this.loading = true
      try {
        const conversations = await listConversations(token)
        const items = await Promise.all(
          conversations.map(async (conv) => {
            const messages = await listMessages(token, conv.id)
            const last = messages.length > 0 ? messages[messages.length - 1] : null
            return {
              id: conv.id,
              status: conv.status,
              startedAt: conv.created_at,
              endedAt: last ? last.created_at : null,
              preview: last ? last.content : '',
            } as ConversationHistoryItem
          }),
        )
        // 历史会话按时间倒序（最新在前）
        this.history = items.sort((a, b) => b.startedAt.localeCompare(a.startedAt))
      } finally {
        this.loading = false
      }
    },
  },
})
