import { defineStore } from 'pinia'

import { listQueueItems, type QueueItem } from '../api/agents'

/** 回呼请求工单展示模型（US-29 底部独立分组）。 */
export interface CallbackTicket {
  ticket_id: number
  customer_phone: string
  created_at: string
}

/**
 * TODO(backend #42)：坐席回呼查询端点未落地（/tickets 为客户视角，坐席 JWT → 401），
 * v1 以本地占位数据驱动回呼分组 UI；#42 落地后替换为 api 拉取。
 */
const MOCK_CALLBACK_TICKETS: CallbackTicket[] = [
  { ticket_id: 101, customer_phone: '139****0002', created_at: '2026-08-03T02:00:00Z' },
  { ticket_id: 102, customer_phone: '158****0013', created_at: '2026-08-03T02:30:00Z' },
]

/**
 * 待接入队列 store（US-20/21/29）。
 *
 * - items：待接入 Handoff 会话（GET /agents/queues 真契约）。
 * - unreadIds：新进入项（本轮刷新新出现的 conversation_id）未读高亮
 *   `semantic-info-tint-bg`（PRD 状态策略「Handoff 等待」行）。
 * - callbacks：回呼请求分组（mock 数据源，见上 TODO）。
 * - allBusy：全忙线变体标志（后端坐席状态聚合未落地，先由本地驱动；
 *   未来可经 agent.status / 队列响应派生）。
 */
export const useQueueStore = defineStore('queue', {
  state: () => ({
    items: [] as QueueItem[],
    callbacks: MOCK_CALLBACK_TICKETS as CallbackTicket[],
    loading: false,
    allBusy: false,
    /** 新进入项 conversation_id 集合（未读高亮）。 */
    unreadIds: [] as number[],
    /** 上一轮 items 的 id 快照，用于刷新时识别新进入项。 */
    _seenIds: [] as number[],
  }),
  getters: {
    /** 待接入 N 单（统计条计数 = 待接入列表长度，不含回呼分组）。 */
    count: (s) => s.items.length,
  },
  actions: {
    /** 拉取待接入队列；新出现的项记入 unreadIds（未读高亮）。 */
    async load(token: string) {
      this.loading = true
      try {
        const items = await listQueueItems(token)
        const ids = items.map((i) => i.conversation_id)
        this.unreadIds = ids.filter((id) => !this._seenIds.includes(id))
        this._seenIds = ids
        this.items = items
      } finally {
        this.loading = false
      }
    },
    /** 接入/浏览后清除未读标记。 */
    markRead(id: number) {
      this.unreadIds = this.unreadIds.filter((x) => x !== id)
    },
  },
})
