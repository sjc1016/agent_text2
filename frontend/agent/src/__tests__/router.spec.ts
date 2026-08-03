import { describe, it, expect } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ElementPlus from 'element-plus'

import { routes } from '../router'

async function mountRoute(path: string) {
  setActivePinia(createPinia())
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(
    { template: '<router-view />' },
    { global: { plugins: [router, ElementPlus] } },
  )
  return { wrapper, router }
}

describe('router — login-variant', () => {
  it('/login 脱离壳层：无顶栏无侧栏，渲染全屏登录页', async () => {
    const { wrapper } = await mountRoute('/login')

    expect(wrapper.find('[data-testid="app-header"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="app-sidebar"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="login-page"]').exists()).toBe(true)
  })

  it('功能页路由继承壳层：/queue 渲染顶栏 + 侧栏 + 内容区', async () => {
    const { wrapper } = await mountRoute('/queue')

    expect(wrapper.find('[data-testid="app-header"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="app-sidebar"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="app-content"]').exists()).toBe(true)
  })

  it('根路径重定向到 /queue（待接入为坐席默认页）', async () => {
    const { router } = await mountRoute('/')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/queue')
  })
})
