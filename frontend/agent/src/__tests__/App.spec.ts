import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import App from '../App.vue'
import { routes } from '../router'

// QueueView onMounted 触发队列拉取（#20），此处 mock 避免真实 fetch。
vi.mock('../api/agents', () => ({
  listQueueItems: vi.fn().mockResolvedValue([]),
}))

describe('App', () => {
  it('挂载路由渲染坐席工作台壳层', async () => {
    setActivePinia(createPinia())
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push('/queue')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })

    expect(wrapper.find('[data-testid="app-header"]').exists()).toBe(true)
  })
})
