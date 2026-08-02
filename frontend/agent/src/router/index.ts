import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import LoginView from '../views/LoginView.vue'
import QueueView from '../views/QueueView.vue'
import ActiveChatView from '../views/ActiveChatView.vue'
import TicketsView from '../views/TicketsView.vue'
import HistoryView from '../views/HistoryView.vue'
import { setupRouteLoadingGuard } from './guards'

/**
 * agent-console 路由表（PRD 页面清单 §app-shell 壳层变体）。
 *
 * - `/login` 脱离壳层全屏（PRD：壳层变体 login 完全脱离壳层）。
 * - `/queue` `/active-chat` `/tickets` `/history` 继承 AppShell，对应侧栏四菜单。
 * - 根路径重定向到 `/queue`（待接入为坐席默认页）。
 * - 功能页内容由后续 UI-A-* issue 实现，本 issue 仅交付壳层占位。
 */
export const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: LoginView,
  },
  {
    path: '/',
    component: AppShell,
    children: [
      { path: '', redirect: '/queue' },
      { path: 'queue', name: 'queue', component: QueueView },
      { path: 'active-chat', name: 'active-chat', component: ActiveChatView },
      { path: 'tickets', name: 'tickets', component: TicketsView },
      { path: 'history', name: 'history', component: HistoryView },
    ],
  },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由切换加载守卫（PRD 状态策略「加载中」）。守卫在导航时执行，
// 届时 pinia 已激活（main.ts 先安装 pinia）。
setupRouteLoadingGuard(router)

export default router
