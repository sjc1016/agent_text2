import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createPinia, setActivePinia, type Pinia } from 'pinia'

import QueueView from '../views/QueueView.vue'
import { useQueueStore } from '../stores/queue'
import { listQueueItems, type QueueItem } from '../api/agents'

/**
 * #20 UI-A-3 循环：QueueView（States 矩阵逐行验证）。
 *
 * 行序循环：default → new-item-highlight → empty → loading → all-busy。
 * 测行为不测像素：data-testid 结构 + 可观察行为（接入跳转 / 拨打 / 刷新）。
 * 数据缺口：转接原因 + 回呼请求分组由本地 mock 驱动（backend issue #42）。
 */

vi.mock('../api/agents', () => ({
  listQueueItems: vi.fn(),
}))

const mockedListQueueItems = vi.mocked(listQueueItems)

let router: Router

/** 挂载 QueueView；onMounted 触发 queue.load()（mock api 返回注入数据）。 */
async function mountQueue(): Promise<{ wrapper: ReturnType<typeof mount>; pinia: Pinia }> {
  const pinia: Pinia = createPinia()
  setActivePinia(pinia)
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/queue', component: QueueView },
      {
        path: '/active-chat',
        name: 'active-chat',
        component: { template: '<div>active-chat</div>' },
      },
    ],
  })
  await router.push('/queue')
  await router.isReady()
  const wrapper = mount(QueueView, {
    global: { plugins: [router, pinia] },
  })
  await flushPromises()
  return { wrapper, pinia }
}

function queueItem(id: number, overrides: Partial<QueueItem> = {}): QueueItem {
  return {
    conversation_id: id,
    status: 'handed_off',
    created_at: '2026-08-03T01:00:00Z',
    customer_id: id * 10,
    customer_phone: '138****0001',
    last_user_message: '用户请求转人工',
    ...overrides,
  }
}

beforeEach(() => {
  localStorage.clear()
  mockedListQueueItems.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('QueueView — default state（US-20/21/29）', () => {
  it('渲染统计条（待接入 N 单 + 辅助文案 + 刷新）与待接入列表（接入按钮）及回呼请求分组（拨打按钮）', async () => {
    mockedListQueueItems.mockResolvedValue([
      queueItem(1),
      queueItem(2, { last_user_message: '故障报修', customer_id: null }),
    ])
    const { wrapper } = await mountQueue()

    // 统计条：待接入 N 单 + 辅助文案 + 刷新按钮
    const stats = wrapper.find('[data-testid="queue-stats"]')
    expect(stats.exists()).toBe(true)
    expect(stats.text()).toContain('待接入 2 单')
    expect(stats.text()).toContain('非服务时间进入队列的会话次日接入')
    expect(stats.find('[data-testid="queue-refresh-btn"]').exists()).toBe(true)

    // 待接入列表：每行主文案（会话起因摘要）+ 接入按钮
    const items = wrapper.findAll('[data-testid="queue-item"]')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('用户请求转人工')
    expect(items[1].text()).toContain('故障报修')
    expect(items[0].find('[data-testid="queue-accept-btn"]').exists()).toBe(true)

    // 回呼请求分组：标题 + 拨打按钮
    const group = wrapper.find('[data-testid="queue-callback-group"]')
    expect(group.exists()).toBe(true)
    expect(group.text()).toContain('回呼请求')
    expect(group.findAll('[data-testid="queue-callback-item"]').length).toBeGreaterThan(0)
    expect(group.find('[data-testid="queue-callback-call-btn"]').exists()).toBe(true)
  })

  it('点击「接入」跳转 active-chat 并携带 conversation_id', async () => {
    mockedListQueueItems.mockResolvedValue([queueItem(7)])
    const { wrapper } = await mountQueue()

    await wrapper.findAll('[data-testid="queue-accept-btn"]')[0].trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/active-chat')
    expect(router.currentRoute.value.query.conversation_id).toBe('7')
  })
})

describe('QueueView — new-item-highlight（PRD 状态策略 Handoff 等待行）', () => {
  it('新进入项高亮未读态（semantic-info-tint-bg），接入后清除', async () => {
    mockedListQueueItems.mockResolvedValue([queueItem(1), queueItem(2)])
    const { wrapper } = await mountQueue()

    const items = wrapper.findAll('[data-testid="queue-item"]')
    expect(items[0].classes()).toContain('queue-item--unread')
    expect(items[1].classes()).toContain('queue-item--unread')

    await items[0].find('[data-testid="queue-accept-btn"]').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('[data-testid="queue-item"]')[0].classes()).not.toContain(
      'queue-item--unread',
    )
  })
})

describe('QueueView — empty（PRD §queue 空状态变体）', () => {
  it('无待接入时居中 empty-state 插画 + 主文案「暂无待接入会话」+ 辅助文案', async () => {
    mockedListQueueItems.mockResolvedValue([])
    const { wrapper } = await mountQueue()

    const empty = wrapper.find('[data-testid="queue-empty"]')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('暂无待接入会话')
    expect(empty.text()).toContain('有新转接会话将在此显示')
    expect(empty.find('[data-testid="queue-empty-illustration"]').exists()).toBe(true)
  })
})

describe('QueueView — loading（PRD §queue 加载变体 / DESIGN §5.10 骨架屏）', () => {
  it('列表加载中显示骨架屏，加载完成后渲染列表', async () => {
    let resolveLoad!: (value: QueueItem[]) => void
    mockedListQueueItems.mockReturnValue(
      new Promise<QueueItem[]>((resolve) => {
        resolveLoad = resolve
      }),
    )
    const { wrapper } = await mountQueue()

    // 加载中：骨架屏可见，列表与空状态不可见
    expect(wrapper.find('[data-testid="queue-skeleton"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="queue-list"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="queue-empty"]').exists()).toBe(false)

    // 加载完成：列表渲染
    resolveLoad([queueItem(3)])
    await flushPromises()
    expect(wrapper.find('[data-testid="queue-skeleton"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-testid="queue-item"]')).toHaveLength(1)
  })
})

describe('QueueView — all-busy（PRD §queue 全部忙线变体）', () => {
  it('全忙线时统计条辅助文案改 Warning「当前所有坐席忙线，新会话进入离线兜底」', async () => {
    mockedListQueueItems.mockResolvedValue([queueItem(1)])
    const { wrapper, pinia } = await mountQueue()

    useQueueStore(pinia).allBusy = true
    await nextTick()

    const hint = wrapper.find('[data-testid="queue-stats-hint"]')
    expect(hint.text()).toBe('当前所有坐席忙线，新会话进入离线兜底')
    expect(hint.classes()).toContain('stats-card__hint--warning')
  })
})
