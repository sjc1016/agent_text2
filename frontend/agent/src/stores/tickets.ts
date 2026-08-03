import { defineStore } from 'pinia'

import {
  cancelTicket,
  closeTicket,
  createAgentTicket,
  dispatchTicket,
  dispatchTicketToGroup,
  executeTicket,
  listAgentTickets,
  type AgentTicket,
  type CreateTicketInput,
} from '../api/tickets'

/**
 * 坐席工单 store（#22 UI-A-5）：承载「工单管理」页数据源与交互态。
 *
 * 职责边界：
 *   - tickets：坐席工单列表（US-27，数据源 api/tickets.ts，mock 先行见 #44/#45）。
 *   - loading：列表加载态（States 矩阵 loading → 骨架屏）。
 *   - filters：筛选条件（类型/状态/技能组/关键词，PRD 筛选栏），客户端过滤 filtered。
 *   - selectedId：选中行（States 矩阵 row-selected → 色条 + 背景）。
 *   - 行内操作（US-24/25）：dispatch / close / execute / create，成功后原地更新列表。
 */
export const useTicketsStore = defineStore('tickets', {
  state: () => ({
    tickets: [] as AgentTicket[],
    loading: false,
    /** 筛选条件（PRD 筛选栏：类型/状态/技能组 Select + 搜索框）。 */
    filters: {
      type: 'all',
      status: 'all',
      skillGroup: 'all',
      keyword: '',
    },
    /** 当前选中行 id（row-selected 态；点击行切换）。 */
    selectedId: null as number | null,
  }),
  getters: {
    /** 是否有激活的筛选条件（no-result 态判定：有数据 + 有筛选 + 无匹配）。 */
    hasActiveFilters(state): boolean {
      const f = state.filters
      return f.type !== 'all' || f.status !== 'all' || f.skillGroup !== 'all' || f.keyword !== ''
    },
    /** 筛选后的工单列表（客户端过滤；后端落地后可改为 query 参数，逻辑不变）。 */
    filteredTickets(state): AgentTicket[] {
      const f = state.filters
      return state.tickets.filter((t) => {
        if (f.type !== 'all' && t.ticket_type !== f.type) return false
        if (f.status !== 'all' && t.status !== f.status) return false
        if (f.skillGroup !== 'all' && t.skill_group !== f.skillGroup) return false
        if (
          f.keyword !== '' &&
          !t.content.includes(f.keyword) &&
          !(t.customer_phone ?? '').includes(f.keyword)
        ) {
          return false
        }
        return true
      })
    },
  },
  actions: {
    /** 拉取坐席工单列表（US-27）。 */
    async load(token: string): Promise<void> {
      this.loading = true
      try {
        this.tickets = await listAgentTickets(token)
      } finally {
        this.loading = false
      }
    },

    /** 重置全部筛选条件（「重置」文字按钮 / 无结果态「清除筛选」）。 */
    resetFilters(): void {
      this.filters = { type: 'all', status: 'all', skillGroup: 'all', keyword: '' }
    },

    /** 点击列表行：选中当前行（row-selected 态）。 */
    selectRow(ticketId: number): void {
      this.selectedId = ticketId
    },

    /** 派单（US-24）：待派单 → 已派单。 */
    async dispatch(ticketId: number, token: string): Promise<void> {
      const updated = await dispatchTicket(ticketId, token)
      this.replaceTicket(updated)
    },

    /** 派单到技能组（详情页操作区 US-24）：待派单 → 已派单 + 记录技能组。 */
    async dispatchToGroup(ticketId: number, skillGroup: string, token: string): Promise<void> {
      const updated = await dispatchTicketToGroup(ticketId, skillGroup, token)
      this.replaceTicket(updated)
    },

    /** 关闭（US-24）：待确认 → 已关闭。 */
    async close(ticketId: number, token: string): Promise<void> {
      const updated = await closeTicket(ticketId, token)
      this.replaceTicket(updated)
    },

    /** 取消工单（详情页操作区 US-24）：非终态 → 已取消。 */
    async cancel(ticketId: number, token: string): Promise<void> {
      const updated = await cancelTicket(ticketId, token)
      this.replaceTicket(updated)
    },

    /** 服务密码复核通过后执行（US-25）：待执行 → 执行中。 */
    async execute(ticketId: number, servicePassword: string, token: string): Promise<void> {
      const updated = await executeTicket(ticketId, servicePassword, token)
      this.replaceTicket(updated)
    },

    /** 创建工单（US-23）：成功后追加列表头部。 */
    async create(input: CreateTicketInput, token: string): Promise<void> {
      const created = await createAgentTicket(input, token)
      this.tickets = [created, ...this.tickets]
    },

    /** 行内操作成功后原地替换工单（保持排序与选中态）。 */
    replaceTicket(updated: AgentTicket): void {
      this.tickets = this.tickets.map((t) => (t.id === updated.id ? updated : t))
    },
  },
})
