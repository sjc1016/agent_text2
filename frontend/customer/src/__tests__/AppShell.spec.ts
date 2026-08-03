import { describe, it, expect } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import ElementPlus from 'element-plus'

import AppShell from '../components/AppShell.vue'
import { useSessionStore } from '../stores/session'
import { useUiStore } from '../stores/ui'
import type { ConversationState } from 'shared/events'

/** 占位视图，仅用于测试路由切换的可观察行为。 */
const StubView = defineComponent({
  name: 'StubView',
  template: '<div data-testid="stub-view">stub</div>',
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

async function mountShell(initial = '/chat') {
  setActivePinia(createPinia())
  const router = makeRouter()
  await router.push(initial)
  await router.isReady()
  const wrapper = mount(
    { template: '<router-view />' },
    { global: { plugins: [router, ElementPlus] } },
  )
  return { wrapper, router }
}

/** 设置会话状态并返回会话 store，用于驱动顶栏会话标题/徽章变体。 */
function setSession(state: ConversationState, maskedPhone = '') {
  const session = useSessionStore()
  session.conversationState = state
  session.maskedPhone = maskedPhone
  return session
}

describe('AppShell — default state', () => {
  it('渲染顶栏/内容区/底栏 Tab 三段分区', async () => {
    const { wrapper } = await mountShell('/chat')

    expect(wrapper.find('[data-testid="app-header"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="app-content"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="app-bottom-tab"]').exists()).toBe(true)
  })

  it('底栏含三个 Tab：会话/我的工单/我的，各含 24px 图标', async () => {
    const { wrapper } = await mountShell('/chat')

    const tabs = wrapper.findAll('[data-testid="bottom-tab-item"]')
    expect(tabs).toHaveLength(3)
    expect(tabs[0].text()).toContain('会话')
    expect(tabs[1].text()).toContain('我的工单')
    expect(tabs[2].text()).toContain('我的')

    // DESIGN.md §5.5 底栏 Tab：每个 Tab 渲染 24px 线性图标（el-icon 以 font-size 定尺寸）
    for (const tab of tabs) {
      const icon = tab.find('.bottom-tab-item__icon')
      expect(icon.exists()).toBe(true)
      expect(icon.find('svg').exists()).toBe(true)
      expect(icon.attributes('style')).toContain('font-size: 24px')
    }
  })

  it('点击「我的工单」Tab 切换路由到 /tickets', async () => {
    const { wrapper, router } = await mountShell('/chat')

    const tabs = wrapper.findAll('[data-testid="bottom-tab-item"]')
    await tabs[1].trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/tickets')
  })
})

describe('AppShell — session-state-variants', () => {
  it('未认证：顶栏标题「在线咨询」+ Neutral 徽章「访客」', async () => {
    const { wrapper } = await mountShell('/chat')
    setSession('unauthenticated')
    await flushPromises()

    const header = wrapper.find('[data-testid="app-header"]')
    expect(header.text()).toContain('在线咨询')

    const badge = wrapper.find('[data-testid="session-badge"]')
    expect(badge.attributes('data-variant')).toBe('neutral')
    expect(badge.text()).toContain('访客')
  })

  it('已认证：顶栏标题号码脱敏 + Primary 徽章「已认证」', async () => {
    const { wrapper } = await mountShell('/chat')
    setSession('authenticated', '138****1234')
    await flushPromises()

    const header = wrapper.find('[data-testid="app-header"]')
    expect(header.text()).toContain('138****1234')

    const badge = wrapper.find('[data-testid="session-badge"]')
    expect(badge.attributes('data-variant')).toBe('primary')
    expect(badge.text()).toContain('已认证')
  })

  it('转接中：顶栏标题「坐席服务中」+ Info 徽章「转接中」', async () => {
    const { wrapper } = await mountShell('/chat')
    setSession('handed_off')
    await flushPromises()

    const header = wrapper.find('[data-testid="app-header"]')
    expect(header.text()).toContain('坐席服务中')

    const badge = wrapper.find('[data-testid="session-badge"]')
    expect(badge.attributes('data-variant')).toBe('info')
    expect(badge.text()).toContain('转接中')
  })
})

describe('AppShell — ws-broken', () => {
  it('WS 断线：顶栏显示错误条「连接已断开，正在重连」', async () => {
    const { wrapper } = await mountShell('/chat')
    useUiStore().wsBroken = true
    await flushPromises()

    const bar = wrapper.find('[data-testid="ws-broken-bar"]')
    expect(bar.exists()).toBe(true)
    expect(bar.attributes('data-variant')).toBe('error')
    expect(bar.text()).toContain('连接已断开，正在重连')
  })

  it('WS 恢复：错误条消失', async () => {
    const { wrapper } = await mountShell('/chat')
    const ui = useUiStore()
    ui.wsBroken = true
    await flushPromises()
    expect(wrapper.find('[data-testid="ws-broken-bar"]').exists()).toBe(true)

    ui.wsBroken = false
    await flushPromises()
    expect(wrapper.find('[data-testid="ws-broken-bar"]').exists()).toBe(false)
  })
})
