import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import AppShell from '../components/AppShell.vue'
import ChatView from '../views/ChatView.vue'
import TicketsView from '../views/TicketsView.vue'
import ProfileView from '../views/ProfileView.vue'
import ProfileHistoryView from '../views/ProfileHistoryView.vue'
import AuthView from '../views/AuthView.vue'
import { setupRouteLoadingGuard } from './guards'

/**
 * customer-web 路由表（PRD 页面清单 §app-shell 壳层变体）。
 *
 * - `/auth` 脱离壳层全屏（PRD：壳层变体 auth 完全脱离壳层）。
 * - `/chat` / `/tickets` / `/profile` 继承 AppShell，对应底栏三 Tab；
 *   `/profile/history/:id` 为会话历史只读视图（#11），继承 AppShell 且底栏 Tab 保持「我的」。
 * - 根路径重定向到 `/chat`（对话为用户端主入口）。
 */
export const routes: RouteRecordRaw[] = [
  {
    path: '/auth',
    name: 'auth',
    component: AuthView,
  },
  {
    path: '/',
    component: AppShell,
    children: [
      { path: '', redirect: '/chat' },
      { path: 'chat', name: 'chat', component: ChatView },
      { path: 'tickets', name: 'tickets', component: TicketsView },
      { path: 'profile', name: 'profile', component: ProfileView },
      // 历史会话只读视图（#11：profile 会话历史点击进入；继承壳层，返回回 /profile）
      { path: 'profile/history/:id', name: 'profile-history', component: ProfileHistoryView },
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
