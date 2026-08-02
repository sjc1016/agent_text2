import { defineStore } from 'pinia'

/** 坐席状态三态（PRD app-shell(agent-console)：在线/小休/离线）。 */
export type AgentStatus = 'online' | 'break' | 'offline'

export const agentStatusLabels: Record<AgentStatus, string> = {
  online: '在线',
  break: '小休',
  offline: '离线',
}

/**
 * 坐席工作台全局状态（agent-console app-shell 消费）。
 *
 * 当前职责：
 *   - status：坐席状态切换（US-30），顶栏状态按钮读写；
 *     后续由 WS `agent.status` 事件同步后端（#24 接入）。
 *   - queueUnread：待接入队列未读计数，侧栏「待接入」项右侧 Error 徽章；
 *     后续由 WS 待接入事件更新。
 */
export const useAgentStore = defineStore('agent', {
  state: () => ({
    status: 'online' as AgentStatus,
    queueUnread: 3,
  }),
  getters: {
    statusLabel: (s) => agentStatusLabels[s.status],
  },
  actions: {
    setStatus(status: AgentStatus) {
      this.status = status
    },
  },
})
