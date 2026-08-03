import { defineStore } from 'pinia'

import {
  listTickets,
  listUnreadNotifications,
  type Ticket,
  type TicketNotification,
} from '../api/tickets'

/**
 * tickets store（#16 UI-C-4）：承载「我的工单」页数据源与交互态。
 *
 * 职责边界：
 *   - tickets / notifications：工单列表 + 未读通知（US-14，数据源 api/tickets.ts）。
 *   - loading：列表加载态（States 矩阵 loading → 骨架屏）。
 *   - expandedId：当前展开的工单行（内联嵌套卡片，点击行展开/收起）。
 *   - 认证态不在此判定：视图层按 session.isAuthenticated 路由到未认证变体。
 */
export const useTicketsStore = defineStore('tickets', {
  state: () => ({
    tickets: [] as Ticket[],
    notifications: [] as TicketNotification[],
    loading: false,
    /** 当前展开的工单 id（null 表示全部收起；再次点击同一行收起）。 */
    expandedId: null as number | null,
  }),
  getters: {
    /** 未读通知（预览条数据源，按 created_at 倒序）。 */
    unreadNotifications(state): TicketNotification[] {
      return state.notifications
        .filter((n) => !n.read)
        .slice()
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
    },
    /** 某工单的关联通知（展开卡片「关联通知」段）。 */
    notificationsFor(state) {
      return (ticketId: number): TicketNotification[] =>
        state.notifications.filter((n) => n.ticket_id === ticketId)
    },
  },
  actions: {
    /** 拉取工单列表 + 未读通知（并发放置 loading；失败抛出由视图层处理）。 */
    async load(token: string): Promise<void> {
      this.loading = true
      try {
        const [tickets, notifications] = await Promise.all([
          listTickets(token),
          listUnreadNotifications(token),
        ])
        this.tickets = tickets
        this.notifications = notifications
      } finally {
        this.loading = false
      }
    },

    /** 点击列表行：同一行展开/收起，其他行展开覆盖（内联嵌套卡片）。 */
    toggleExpand(ticketId: number): void {
      this.expandedId = this.expandedId === ticketId ? null : ticketId
    },

    /** 通知预览条点击：展开对应工单行（跳转到工单上下文）。 */
    expandTicket(ticketId: number): void {
      this.expandedId = ticketId
    },
  },
})
