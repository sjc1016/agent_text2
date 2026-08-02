import type { Router } from 'vue-router'

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
