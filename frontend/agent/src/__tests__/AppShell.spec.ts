import { describe, it, expect } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'

import AppShell from '../components/AppShell.vue'

/** 占位视图，仅用于测试路由切换与壳层渲染的可观察行为。 */
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
          { path: 'queue', component: StubView },
          { path: 'active-chat', component: StubView },
          { path: 'tickets', component: StubView },
          { path: 'history', component: StubView },
        ],
      },
    ],
  })
}

async function mountShell(initial = '/queue') {
  setActivePinia(createPinia())
  const router = makeRouter()
  await router.push(initial)
  await router.isReady()
  const wrapper = mount({ template: '<router-view />' }, { global: { plugins: [router] } })
  return { wrapper, router }
}

describe('AppShell — default state', () => {
  it('渲染顶栏/侧栏/内容区三段分区', async () => {
    const { wrapper } = await mountShell('/queue')

    expect(wrapper.find('[data-testid="app-header"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="app-sidebar"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="app-content"]').exists()).toBe(true)
  })

  it('侧栏含四个菜单：待接入/进行中/工单管理/历史会话', async () => {
    const { wrapper } = await mountShell('/queue')

    const items = wrapper.findAll('[data-testid="sidebar-menu-item"]')
    expect(items).toHaveLength(4)
    expect(items[0].text()).toContain('待接入')
    expect(items[1].text()).toContain('进行中')
    expect(items[2].text()).toContain('工单管理')
    expect(items[3].text()).toContain('历史会话')
  })
})

describe('AppShell — navigation (US-19/US-30)', () => {
  it('点击「工单管理」菜单切换路由到 /tickets', async () => {
    const { wrapper, router } = await mountShell('/queue')

    await wrapper.findAll('[data-testid="sidebar-menu-item"]')[2].trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/tickets')
  })

  it('点击「历史会话」菜单切换路由到 /history', async () => {
    const { wrapper, router } = await mountShell('/queue')

    await wrapper.findAll('[data-testid="sidebar-menu-item"]')[3].trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/history')
  })

  it('当前路由对应菜单为选中态（router-link-active）', async () => {
    const { wrapper } = await mountShell('/tickets')

    const items = wrapper.findAll('[data-testid="sidebar-menu-item"]')
    expect(items[2].classes()).toContain('router-link-active')
    expect(items[0].classes()).not.toContain('router-link-active')
  })
})

describe('AppShell — agent-status (US-30)', () => {
  it('顶栏显示坐席状态按钮，默认在线', async () => {
    const { wrapper } = await mountShell('/queue')

    const btn = wrapper.find('[data-testid="agent-status-btn"]')
    expect(btn.exists()).toBe(true)
    expect(btn.attributes('data-variant')).toBe('online')
    expect(btn.text()).toContain('在线')
  })

  it('点击状态按钮展开下拉，选择「小休」后状态切换生效', async () => {
    const { wrapper } = await mountShell('/queue')

    await wrapper.find('[data-testid="agent-status-btn"]').trigger('click')
    await flushPromises()

    const dropdown = wrapper.find('[data-testid="agent-status-dropdown"]')
    expect(dropdown.exists()).toBe(true)

    const options = dropdown.findAll('[data-testid="agent-status-option"]')
    expect(options.map((o) => o.text())).toEqual(['在线', '小休', '离线'])

    await options[1].trigger('click')
    await flushPromises()

    const btn = wrapper.find('[data-testid="agent-status-btn"]')
    expect(btn.attributes('data-variant')).toBe('break')
    expect(btn.text()).toContain('小休')
  })
})

describe('AppShell — queue-unread', () => {
  it('「待接入」菜单项右侧显示未读计数 Error 徽章', async () => {
    const { wrapper } = await mountShell('/queue')

    const items = wrapper.findAll('[data-testid="sidebar-menu-item"]')
    const badge = items[0].find('[data-testid="sidebar-unread-badge"]')

    expect(badge.exists()).toBe(true)
    expect(badge.attributes('data-variant')).toBe('error')
    expect(badge.text()).toBe('3')
  })

  it('其余菜单项不显示未读徽章', async () => {
    const { wrapper } = await mountShell('/queue')

    const items = wrapper.findAll('[data-testid="sidebar-menu-item"]')
    for (const item of items.slice(1)) {
      expect(item.find('[data-testid="sidebar-unread-badge"]').exists()).toBe(false)
    }
  })
})

describe('AppShell — search-focus', () => {
  it('顶栏含全局搜索框，placeholder「搜索会话/工单/客户」', async () => {
    const { wrapper } = await mountShell('/queue')

    const input = wrapper.find('[data-testid="global-search-input"]')
    expect(input.exists()).toBe(true)
    expect(input.attributes('placeholder')).toBe('搜索会话/工单/客户')
  })

  it('聚焦搜索框：展开态 class + 下拉结果面板出现', async () => {
    const { wrapper } = await mountShell('/queue')

    const input = wrapper.find('[data-testid="global-search-input"]')
    await input.trigger('focus')
    await flushPromises()

    expect(input.classes()).toContain('global-search__input--expanded')
    expect(wrapper.find('[data-testid="global-search-panel"]').exists()).toBe(true)
  })
})
