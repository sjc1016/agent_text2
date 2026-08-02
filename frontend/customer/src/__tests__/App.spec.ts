import { describe, it, expect } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, type Component } from 'vue'

import App from '../App.vue'
import AppShell from '../components/AppShell.vue'
import { setupRouteLoadingGuard } from '../router/guards'
import { routes } from '../router'
import { useUiStore } from '../stores/ui'

const StubView = defineComponent({
  name: 'StubView',
  template: '<div data-testid="stub-view"/>',
})

function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/',
        component: AppShell,
        children: [
          { path: 'chat', component: StubView },
          { path: 'tickets', component: StubView },
          { path: 'profile', component: StubView },
        ],
      },
    ],
  })
}

/** App 根出口冒烟：App 经 router 渲染，/chat 下应挂载 AppShell 壳层。 */
describe('App', () => {
  it('经路由渲染 /chat 时挂载 AppShell 壳层', async () => {
    setActivePinia(createPinia())
    const router = makeRouter()
    await router.push('/chat')
    await router.isReady()

    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="app-header"]').exists()).toBe(true)
  })
})

describe('App — loading state（路由切换全屏 spinner + 遮罩）', () => {
  it('路由加载中：显示全屏 spinner 遮罩', async () => {
    setActivePinia(createPinia())
    const ui = useUiStore()
    ui.routeLoading = true

    const router = makeRouter()
    await router.push('/chat')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="route-loading-overlay"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="route-loading-spinner"]').exists()).toBe(true)
  })

  it('路由加载结束：遮罩消失', async () => {
    setActivePinia(createPinia())
    const ui = useUiStore()

    const router = makeRouter()
    await router.push('/chat')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    ui.routeLoading = true
    await flushPromises()
    expect(wrapper.find('[data-testid="route-loading-overlay"]').exists()).toBe(true)

    ui.routeLoading = false
    await flushPromises()
    expect(wrapper.find('[data-testid="route-loading-overlay"]').exists()).toBe(false)
  })

  it('路由切换触发 loading 流程：切换中显示遮罩，切换完成消失', async () => {
    setActivePinia(createPinia())
    const ui = useUiStore()

    let resolveLazy!: () => void
    const LazyView = defineComponent({ template: '<div/>' })
    const lazyComponent = () =>
      new Promise<{ default: Component }>((resolve) => {
        resolveLazy = () => resolve({ default: LazyView })
      })

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/',
          component: AppShell,
          children: [
            { path: 'chat', component: StubView },
            { path: 'tickets', component: StubView },
            { path: 'profile', component: StubView },
            { path: 'slow', component: lazyComponent },
          ],
        },
      ],
    })
    setupRouteLoadingGuard(router)

    await router.push('/chat')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()
    expect(ui.routeLoading).toBe(false)

    // 发起导航到 lazy 路由（beforeEach 置 loading=true，组件挂起未解析）
    const navPromise = router.push('/slow')
    await flushPromises()

    expect(ui.routeLoading).toBe(true)
    expect(wrapper.find('[data-testid="route-loading-overlay"]').exists()).toBe(true)

    // 解析 lazy 组件 → afterEach 置 loading=false
    resolveLazy()
    await navPromise
    await flushPromises()

    expect(ui.routeLoading).toBe(false)
    expect(wrapper.find('[data-testid="route-loading-overlay"]').exists()).toBe(false)
  })
})

describe('AppShell — auth 壳层变体（脱离壳层全屏）', () => {
  it('/auth 脱离壳层：无顶栏无底栏，渲染 AuthView', async () => {
    setActivePinia(createPinia())
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push('/auth')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="app-header"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="app-bottom-tab"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="auth-view"]').exists()).toBe(true)
  })

  it('/chat 继承壳层：有顶栏与底栏，渲染 ChatView', async () => {
    setActivePinia(createPinia())
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push('/chat')
    await router.isReady()
    const wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-testid="app-header"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="app-bottom-tab"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="chat-view"]').exists()).toBe(true)
  })

  it('根路径 / 重定向到 /chat', async () => {
    setActivePinia(createPinia())
    const router = createRouter({ history: createMemoryHistory(), routes })
    await router.push('/')
    await router.isReady()
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/chat')
  })
})
