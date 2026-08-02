<script setup lang="ts">
import { ref } from 'vue'
import { RouterView, RouterLink } from 'vue-router'

import { useAgentStore, agentStatusLabels, type AgentStatus } from '../stores/agent'

const agent = useAgentStore()

interface MenuItem {
  to: string
  label: string
  menu: string
}

/** 侧栏四菜单，对应 PRD app-shell(agent-console)「待接入/进行中/工单管理/历史会话」。 */
const menus: MenuItem[] = [
  { to: '/queue', label: '待接入', menu: 'queue' },
  { to: '/active-chat', label: '进行中', menu: 'active-chat' },
  { to: '/tickets', label: '工单管理', menu: 'tickets' },
  { to: '/history', label: '历史会话', menu: 'history' },
]

/** 坐席状态下拉（US-30：在线/小休/离线 切换）。 */
const statusOptions: { value: AgentStatus; label: string }[] = (
  Object.keys(agentStatusLabels) as AgentStatus[]
).map((value) => ({ value, label: agentStatusLabels[value] }))
const statusOpen = ref(false)

function selectStatus(status: AgentStatus) {
  agent.setStatus(status)
  statusOpen.value = false
}

/** 全局搜索：聚焦展开 240→320px + 下拉面板（PRD 状态策略「搜索展开」行）。 */
const searchFocused = ref(false)
</script>

<template>
  <div class="app-shell">
    <header data-testid="app-header" class="app-header">
      <div class="app-header__brand">
        <span class="app-header__logo" aria-hidden="true" />
        <span class="app-header__title">客服工作台</span>
      </div>

      <div class="global-search">
        <span class="global-search__icon" aria-hidden="true" />
        <input
          data-testid="global-search-input"
          class="global-search__input"
          :class="{ 'global-search__input--expanded': searchFocused }"
          type="text"
          placeholder="搜索会话/工单/客户"
          @focus="searchFocused = true"
          @blur="searchFocused = false"
        />
        <div
          v-if="searchFocused"
          data-testid="global-search-panel"
          class="global-search__panel"
          @mousedown.prevent
        >
          <div class="global-search__empty">无匹配结果</div>
        </div>
      </div>

      <div class="app-header__right">
        <div class="agent-status">
          <button
            data-testid="agent-status-btn"
            :data-variant="agent.status"
            class="agent-status__btn"
            :class="`agent-status__btn--${agent.status}`"
            type="button"
            @click="statusOpen = !statusOpen"
          >
            <span class="agent-status__dot" aria-hidden="true" />
            <span>{{ agent.statusLabel }}</span>
          </button>
          <div v-if="statusOpen" data-testid="agent-status-dropdown" class="agent-status__dropdown">
            <button
              v-for="opt in statusOptions"
              :key="opt.value"
              data-testid="agent-status-option"
              :data-status="opt.value"
              class="agent-status__option"
              type="button"
              @click="selectStatus(opt.value)"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>

        <div class="agent-identity">
          <span class="agent-identity__avatar" aria-hidden="true" />
          <span class="agent-identity__name">工号 1001</span>
        </div>

        <button data-testid="agent-logout-btn" class="agent-logout" type="button">登出</button>
      </div>
    </header>

    <div class="app-body">
      <nav data-testid="app-sidebar" class="app-sidebar">
        <RouterLink
          v-for="item in menus"
          :key="item.to"
          :to="item.to"
          data-testid="sidebar-menu-item"
          :data-menu="item.menu"
          class="sidebar-menu-item"
        >
          <span class="sidebar-menu-item__label">{{ item.label }}</span>
          <span
            v-if="item.menu === 'queue' && agent.queueUnread > 0"
            data-testid="sidebar-unread-badge"
            data-variant="error"
            class="sidebar-unread-badge"
          >
            {{ agent.queueUnread }}
          </span>
        </RouterLink>
      </nav>

      <main data-testid="app-content" class="app-content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
/* 壳层三段分区：56px 顶栏 + 200px 侧栏 + flex 内容区（DESIGN.md §5.5 导航）。 */
.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #f9fafb;
}

.app-header {
  height: 56px;
  background: #ffffff;
  border-bottom: 1px solid #f3f4f6;
  display: flex;
  align-items: center;
  padding: 0 24px;
  flex-shrink: 0;
  gap: 24px;
}

.app-header__brand {
  display: flex;
  align-items: center;
  gap: 8px;
}

.app-header__logo {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: #1a6fff;
}

.app-header__title {
  color: #1f2937;
  font-size: 16px;
  font-weight: 600;
}

.app-header__right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 16px;
}

/* 全局搜索框（DESIGN.md §5.7 搜索框）：胶囊 32px 高，聚焦展开 240→320px + shadow-focus。 */
.global-search {
  position: relative;
  display: flex;
  align-items: center;
}

.global-search__icon {
  position: absolute;
  left: 12px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 1.5px solid #6b7280;
  pointer-events: none;
}

.global-search__icon::after {
  content: '';
  position: absolute;
  right: -4px;
  bottom: -3px;
  width: 5px;
  height: 1.5px;
  background: #6b7280;
  transform: rotate(45deg);
}

.global-search__input {
  width: 240px;
  height: 32px;
  border: none;
  border-radius: 16px;
  background: #f3f4f6;
  padding: 0 12px 0 36px;
  font-size: 13px;
  color: #1f2937;
  transition: width 0.2s ease;
}

.global-search__input::placeholder {
  color: #9ca3af;
}

.global-search__input--expanded {
  width: 320px;
  background: #ffffff;
  box-shadow: 0 0 0 2px #c9deff;
}

.global-search__panel {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  width: 320px;
  background: #ffffff;
  box-shadow:
    0 4px 6px rgba(0, 0, 0, 0.07),
    0 2px 4px rgba(0, 0, 0, 0.04);
  border-radius: 8px;
  padding: 8px;
  z-index: 20;
}

.global-search__empty {
  text-align: center;
  font-size: 14px;
  color: #9ca3af;
  padding: 16px 0;
}

/* 坐席状态切换（US-30）：在线 semantic-success / 小休 semantic-warning / 离线 Neutral。 */
.agent-status {
  position: relative;
}

.agent-status__btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 40px;
  padding: 0 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  font-size: 14px;
  color: #6b7280;
  cursor: pointer;
}

.agent-status__btn:hover {
  background: #f3f4f6;
}

.agent-status__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #6b7280;
}

/* 在线 semantic-success / 小休 semantic-warning（离线沿用 Neutral 500 默认色）。 */
.agent-status__btn--online {
  color: #2e7d32;
}

.agent-status__btn--online .agent-status__dot {
  background: #2e7d32;
}

.agent-status__btn--break {
  color: #f9a825;
}

.agent-status__btn--break .agent-status__dot {
  background: #f9a825;
}

.agent-status__dropdown {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  width: 120px;
  background: #ffffff;
  box-shadow:
    0 4px 6px rgba(0, 0, 0, 0.07),
    0 2px 4px rgba(0, 0, 0, 0.04);
  border-radius: 8px;
  padding: 4px;
  z-index: 20;
}

.agent-status__option {
  width: 100%;
  height: 36px;
  border: none;
  border-radius: 6px;
  background: transparent;
  text-align: left;
  padding: 0 12px;
  font-size: 14px;
  color: #374151;
  cursor: pointer;
}

.agent-status__option:hover {
  background: #f4f8ff;
  color: #1f2937;
}

.agent-identity {
  display: flex;
  align-items: center;
  gap: 8px;
}

.agent-identity__avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #e0ebff;
}

.agent-identity__name {
  color: #1f2937;
  font-size: 14px;
}

/* 登出：反色按钮（DESIGN.md §5.1，白底 Primary 600 文字）。 */
.agent-logout {
  height: 36px;
  padding: 0 16px;
  border: none;
  border-radius: 6px;
  background: #ffffff;
  color: #0d5be6;
  font-size: 14px;
  cursor: pointer;
}

.agent-logout:hover {
  background: #f3f4f6;
}

.app-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.app-sidebar {
  width: 200px;
  background: #ffffff;
  border-right: 1px solid #f3f4f6;
  padding: 12px 8px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sidebar-menu-item {
  height: 40px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  text-decoration: none;
  color: #374151;
  font-size: 14px;
}

.sidebar-menu-item:hover {
  background: #f4f8ff;
  color: #1f2937;
}

.sidebar-menu-item.router-link-active {
  background: #e0ebff;
  color: #0d5be6;
}

/* 待接入未读徽章：Error 变体（DESIGN.md §5.7，semantic-error-tint-bg 底 + semantic-error 700 文字）。 */
.sidebar-unread-badge {
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 4px;
  background: #fceaea;
  color: #b71c1c;
  font-size: 12px;
  font-weight: 500;
  line-height: 20px;
  text-align: center;
}

.app-content {
  flex: 1;
  overflow: auto;
  background: #f9fafb;
}
</style>
