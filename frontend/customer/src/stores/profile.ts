import { defineStore } from 'pinia'

import { listConversations, listMessages } from '../api/conversations'
import { getCustomerMe, type CustomerMe } from '../api/customers'

/**
 * profile store（#11 UI-C-5）：承载「我的」页数据源与交互态。
 *
 * 职责边界：
 *   - history：会话历史列表（US-17）——经 B2 `GET /conversations` + 每会话
 *     `GET /conversations/{id}/messages` 聚合「起止时间 + 末条消息预览」。
 *   - account：当前客户账户资料（US-17 账号信息）——经 B13 `GET /customers/me`；
 *     planSummary 取 account.plan_name（B13 替换 MOCK_PLAN_SUMMARY 兜底）。
 *   - loading：列表加载态（States 矩阵 loading → 骨架屏）。
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

export const useProfileStore = defineStore('profile', {
  state: () => ({
    history: [] as ConversationHistoryItem[],
    /** 当前客户账户资料（B13 /customers/me；账户卡片套餐简述数据源）。 */
    account: null as CustomerMe | null,
    loading: false,
  }),
  getters: {
    /** 当前套餐简述（账号卡片 Body-sm；B13 起取 /customers/me 的 plan_name）。 */
    planSummary(): string {
      return this.account?.plan_name ?? ''
    },
  },
  actions: {
    /** 拉取账户资料 + 会话历史（并发放置 loading；失败抛出由视图层处理）。 */
    async load(token: string): Promise<void> {
      this.loading = true
      try {
        const [account, conversations] = await Promise.all([
          getCustomerMe(token),
          listConversations(token),
        ])
        this.account = account
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
