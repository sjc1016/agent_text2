import type { Router } from 'vue-router'

import { AUTH_EXPIRED_EVENT, useAuthStore } from '../stores/auth'
import { useUiStore } from '../stores/ui'

/**
 * 注册路由加载守卫：导航开始置 routeLoading=true，导航结束置 false。
 *
 * PRD 状态策略「加载中」：路由切换与鉴权用全屏 spinner + neutral-overlay 遮罩。
 * 在 beforeEach 置位、afterEach 复位；lazy 组件加载期间遮罩持续显示。
 *
 * 依赖 pinia 已激活（main.ts 先安装 pinia 再安装 router）。
 */
export function setupRouteLoadingGuard(router: Router): void {
  router.beforeEach(() => {
    useUiStore().startRouteLoading()
  })
  router.afterEach(() => {
    useUiStore().endRouteLoading()
  })
}

/**
 * 未登录/凭证失效统一跳转目标：`/login?redirect=<原目标 fullPath>`。
 *
 * 鉴权守卫（验收标准 1/2）与凭证失效监听（验收标准 4）复用同一构造，
 * 保证「登录成功后跳回登录前想访问的目标路由」（验收标准 3）链路一致。
 */
export function buildLoginRedirect(fullPath: string): {
  name: 'login'
  query: { redirect: string }
} {
  return { name: 'login', query: { redirect: fullPath } }
}

/** 校验 redirect 查询参数：仅接受站内路径（避免外部跳转，回退工作台首页）。 */
function validateRedirect(raw: unknown): string | null {
  return typeof raw === 'string' && raw.startsWith('/') ? raw : null
}

/**
 * 注册鉴权守卫（issue #58）：未登录拦截受保护路由 → /login，已登录访问 /login → 工作台。
 *
 * - 受保护路由（AppShell 下 `meta.requiresAuth`）无 access token → 重定向 `/login?redirect=…`，
 *   不再渲染工作台、不再触发队列 401 请求（验收标准 1）。
 * - 已登录访问 /login → 回工作台首页 /queue（存在合法 redirect 参数则前往目标，验收标准 2）。
 *
 * 依赖 pinia 已激活（main.ts 先安装 pinia 再安装 router，守卫内 useAuthStore() 可用）。
 */
export function setupAuthGuard(router: Router): void {
  router.beforeEach((to) => {
    const auth = useAuthStore()
    const requiresAuth = to.matched.some((record) => record.meta.requiresAuth)

    if (requiresAuth && !auth.isAuthenticated) {
      return buildLoginRedirect(to.fullPath)
    }
    if (to.name === 'login' && auth.isAuthenticated) {
      return validateRedirect(to.query.redirect) ?? '/queue'
    }
    return undefined
  })
}

/**
 * 注册凭证失效监听（验收标准 4）：API 层收到坐席凭证 401 派发 `AUTH_EXPIRED_EVENT`，
 * 此处清除本地凭证并跳回登录页（复用 buildLoginRedirect，与守卫同一跳转逻辑），
 * 避免停留在报错态。
 */
export function setupAuthExpiredListener(router: Router): void {
  window.addEventListener(AUTH_EXPIRED_EVENT, () => {
    useAuthStore().clearAuth()
    router.replace(buildLoginRedirect(router.currentRoute.value.fullPath))
  })
}
