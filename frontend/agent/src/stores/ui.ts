import { defineStore } from 'pinia'

/**
 * UI store：承载 app-global UI 状态（与具体业务解耦）。
 *
 * 当前职责：
 *   - 路由切换/鉴权加载遮罩（PRD 状态策略「加载中」行：全屏 spinner + neutral-overlay）。
 */
export const useUiStore = defineStore('ui', {
  state: () => ({
    /** 路由切换/鉴权中，渲染全屏 spinner 遮罩。 */
    routeLoading: false,
  }),
  actions: {
    startRouteLoading() {
      this.routeLoading = true
    },
    endRouteLoading() {
      this.routeLoading = false
    },
  },
})
