import { beforeEach, describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import ElementPlus from 'element-plus'

import { routes } from '../router'
import { setupAuthExpiredListener, setupAuthGuard } from '../router/guards'
import { useAuthStore } from '../stores/auth'

// QueueView onMounted 触发队列拉取（#20），此处 mock 避免真实 fetch。
vi.mock('../api/agents', () => ({
  listQueueItems: vi.fn().mockResolvedValue([]),
  listCallbacks: vi.fn().mockResolvedValue([]),
}))

// auth store 从 localStorage 初始化凭证：隔离用例间登录态（守卫用例按需注入）。
beforeEach(() => {
  localStorage.clear()
})

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

/**
 * #58 鉴权守卫用例：注册 setupAuthGuard（+ 凭证失效监听）后按验收标准逐条验证。
 * 挂载前按需注入已登录态（auth store 持久化 localStorage，setActivePinia 后立即写入）。
 */
async function mountWithAuthGuard(
  path: string,
  authed = false,
): Promise<{ router: Router; pinia: Pinia; wrapper: ReturnType<typeof mount> }> {
  const pinia = createPinia()
  setActivePinia(pinia)
  if (authed) {
    useAuthStore().setAuthenticated({ accessToken: 'access-t', refreshToken: 'refresh-t' }, '1001')
  }
  const router = createRouter({ history: createMemoryHistory(), routes })
  setupAuthGuard(router)
  setupAuthExpiredListener(router)
  await router.push(path)
  await router.isReady()
  const wrapper = mount(
    { template: '<router-view />' },
    { global: { plugins: [router, pinia, ElementPlus] } },
  )
  return { router, pinia, wrapper }
}

describe('router — auth guard（issue #58 验收标准 1/2）', () => {
  it('未登录访问 /queue → 重定向 /login?redirect=/queue，不渲染工作台不触发队列请求', async () => {
    const { router, wrapper } = await mountWithAuthGuard('/queue')

    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe('/queue')
    expect(wrapper.find('[data-testid="app-header"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="login-page"]').exists()).toBe(true)
  })

  it('未登录访问 /tickets → 重定向 /login?redirect=/tickets（登录后回目标路由）', async () => {
    const { router } = await mountWithAuthGuard('/tickets')

    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe('/tickets')
  })

  it('未登录访问 /login → 停留登录页（公开路由不拦截）', async () => {
    const { router } = await mountWithAuthGuard('/login')

    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBeUndefined()
  })

  it('已登录访问 /login → 重定向回工作台首页 /queue', async () => {
    const { router } = await mountWithAuthGuard('/login', true)

    expect(router.currentRoute.value.path).toBe('/queue')
  })

  it('已登录访问 /login?redirect=/history → 前往 redirect 目标', async () => {
    const { router } = await mountWithAuthGuard('/login?redirect=/history', true)

    expect(router.currentRoute.value.path).toBe('/history')
  })

  it('已登录访问受保护路由（/queue）→ 放行渲染工作台', async () => {
    const { wrapper } = await mountWithAuthGuard('/queue', true)

    expect(wrapper.find('[data-testid="app-header"]').exists()).toBe(true)
  })
})

describe('router — 登出后受保护路由拦截（issue #60 验收标准 3）', () => {
  it('登出后立即访问受保护路由 → 重定向 /login?redirect=目标', async () => {
    const { router } = await mountWithAuthGuard('/queue', true)
    expect(router.currentRoute.value.path).toBe('/queue')

    useAuthStore().logout()
    await router.push('/tickets')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe('/tickets')
  })
})

describe('router — 凭证失效 401 引导回登录页（issue #58 验收标准 4）', () => {
  it('派发 auth-expired 事件 → 清除本地凭证 + 跳回 /login?redirect=当前路径', async () => {
    const { router, pinia } = await mountWithAuthGuard('/queue', true)
    expect(router.currentRoute.value.path).toBe('/queue')

    window.dispatchEvent(new Event('agent:auth-expired'))
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe('/queue')
    expect(useAuthStore(pinia).isAuthenticated).toBe(false)
    expect(useAuthStore(pinia).accessToken).toBe('')
    expect(localStorage.getItem('agent.auth')).toBeNull()
  })
})
