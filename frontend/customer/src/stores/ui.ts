import { defineStore } from 'pinia'

/**
 * UI store：承载 app-global UI 状态（与具体业务解耦）。
 *
 * 当前职责：
 *   - 路由切换/鉴权加载遮罩（PRD 状态策略「加载中」行：全屏 spinner + neutral-overlay）。
 *   - WebSocket 连接断开顶栏条（PRD 状态策略「错误」行：semantic-error-tint-bg 底）。
 *
 * wsBroken 由 WS 客户端在断线/重连成功时写入（#24 UI-C-3 接入），app-shell 仅消费。
 */
export const useUiStore = defineStore('ui', {
  state: () => ({
    /** 路由切换/鉴权中，渲染全屏 spinner 遮罩。 */
    routeLoading: false,
    /** WebSocket 断线，渲染顶栏错误条。 */
    wsBroken: false,
  }),
  actions: {
    startRouteLoading() {
      this.routeLoading = true
    },
    endRouteLoading() {
      this.routeLoading = false
    },
    setWsBroken(value: boolean) {
      this.wsBroken = value
    },
  },
})
