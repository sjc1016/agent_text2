<script setup lang="ts">
import { RouterView, RouterLink } from 'vue-router'
import { useSessionStore } from '../stores/session'
import { useUiStore } from '../stores/ui'

const session = useSessionStore()
const ui = useUiStore()

interface TabItem {
  to: string
  label: string
  tab: string
}

/** 底栏三 Tab，对应 PRD app-shell「会话/我的工单/我的」。 */
const tabs: TabItem[] = [
  { to: '/chat', label: '会话', tab: 'chat' },
  { to: '/tickets', label: '我的工单', tab: 'tickets' },
  { to: '/profile', label: '我的', tab: 'profile' },
]
</script>

<template>
  <div class="app-shell">
    <header data-testid="app-header" class="app-header">
      <div class="app-header__brand">电信客服</div>
      <div class="app-header__title">{{ session.header.title }}</div>
      <span
        data-testid="session-badge"
        :data-variant="session.header.badgeVariant"
        class="session-badge"
        :class="`session-badge--${session.header.badgeVariant}`"
      >
        {{ session.header.badgeLabel }}
      </span>
    </header>

    <!-- WS 断线顶栏条：PRD 状态策略「错误」行，semantic-error-tint-bg 底 -->
    <div v-if="ui.wsBroken" data-testid="ws-broken-bar" data-variant="error" class="ws-broken-bar">
      连接已断开，正在重连
    </div>

    <main data-testid="app-content" class="app-content">
      <RouterView />
    </main>

    <nav data-testid="app-bottom-tab" class="app-bottom-tab">
      <RouterLink
        v-for="item in tabs"
        :key="item.to"
        :to="item.to"
        data-testid="bottom-tab-item"
        :data-tab="item.tab"
        class="bottom-tab-item"
      >
        <span class="bottom-tab-item__label">{{ item.label }}</span>
      </RouterLink>
    </nav>
  </div>
</template>

<style scoped>
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
  gap: 12px;
  padding: 0 24px;
  flex-shrink: 0;
}

.app-header__brand {
  color: #1a6fff;
  font-weight: 600;
  font-size: 16px;
}

.app-header__title {
  flex: 1;
  color: #1f2937;
  font-size: 14px;
  text-align: center;
}

/* 状态徽章：复用 DESIGN.md §5.7 三变体（Neutral/Primary/Info）。 */
.session-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  line-height: 16px;
}

.session-badge--neutral {
  background: #f3f4f6;
  color: #374151;
}

.session-badge--primary {
  background: #e0ebff;
  color: #0a47b8;
}

.session-badge--info {
  background: #e8f4fb;
  color: #01579b;
}

/* WS 断线条：semantic-error-tint-bg（DESIGN.md §4 #FCEAEA）+ semantic-error 700 文字。 */
.ws-broken-bar {
  background: #fceaea;
  color: #b71c1c;
  font-size: 12px;
  font-weight: 500;
  line-height: 18px;
  padding: 4px 24px;
  text-align: center;
}

.app-content {
  flex: 1;
  overflow: auto;
  background: #f9fafb;
}

.app-bottom-tab {
  height: 48px;
  background: #ffffff;
  border-top: 1px solid #f3f4f6;
  display: flex;
  flex-shrink: 0;
}

.bottom-tab-item {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  text-decoration: none;
  color: #6b7280;
  font-size: 12px;
}

.bottom-tab-item.router-link-active {
  color: #1a6fff;
}
</style>
