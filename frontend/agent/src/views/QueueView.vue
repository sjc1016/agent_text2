<script setup lang="ts">
/**
 * 待接入队列页（US-20/21/29，issue #20）。
 *
 * 继承 agent-console app-shell，侧栏选中「待接入」（路由 /queue）。
 * 规格：PRD 页面清单 §queue「UI 设计描述」+ 变体段；DESIGN.md §5 列表行/按钮/空状态/骨架屏。
 * 数据源：GET /agents/queues（转接原因 reason = Conversation.handoff_reason）+ GET /agents/callbacks。
 */
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import { useQueueStore } from '../stores/queue'
import { handoffReasonLabel } from '../api/activeChat'

const router = useRouter()
const queue = useQueueStore()
const auth = useAuthStore()

/** 坐席 JWT（#18 login 合并后由 auth store 提供；未登录为空串 → 401，待 #21 路由守卫统一处理）。 */
const ACCESS_TOKEN = auth.accessToken

onMounted(() => {
  queue.load(ACCESS_TOKEN)
})

function refresh() {
  queue.load(ACCESS_TOKEN)
}

function accept(conversationId: number) {
  queue.markRead(conversationId)
  router.push({ name: 'active-chat', query: { conversation_id: String(conversationId) } })
}

/** 等待时长（由 created_at 实时计算；不足 1 分钟显示「刚刚」）。 */
function waitLabel(createdAt: string): string {
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(createdAt).getTime()) / 60000))
  return minutes < 1 ? '刚刚' : `等待 ${minutes} 分钟`
}
</script>

<template>
  <div class="queue-page">
    <!-- 顶部统计条：白底 shadow-xs 圆角 8px 卡片（PRD §queue 统计条） -->
    <div data-testid="queue-stats" class="stats-card">
      <div class="stats-card__left">
        <span data-testid="queue-stats-count" class="stats-card__count"
          >待接入 {{ queue.count }} 单</span
        >
        <span
          data-testid="queue-stats-hint"
          class="stats-card__hint"
          :class="{ 'stats-card__hint--warning': queue.allBusy }"
        >
          {{
            queue.allBusy
              ? '当前所有坐席忙线，新会话进入离线兜底'
              : '非服务时间进入队列的会话次日接入'
          }}
        </span>
      </div>
      <button
        data-testid="queue-refresh-btn"
        class="icon-btn icon-btn--refresh"
        type="button"
        aria-label="刷新队列"
        title="刷新"
        @click="refresh"
      />
    </div>

    <!-- 加载变体（PRD §queue 加载变体 / DESIGN §5.10 骨架屏）：列表骨架屏 -->
    <div v-if="queue.loading" data-testid="queue-skeleton" class="skeleton-list" aria-busy="true">
      <div v-for="n in 3" :key="n" class="skeleton-item">
        <div class="skeleton-item__badge" />
        <div class="skeleton-item__lines">
          <div class="skeleton-item__line skeleton-item__line--long" />
          <div class="skeleton-item__line skeleton-item__line--short" />
        </div>
      </div>
    </div>

    <!-- 待接入会话列表（每行 56px 宽松，PRD §queue 列表段） -->
    <div v-if="!queue.loading" data-testid="queue-list" class="queue-list">
      <div
        v-for="item in queue.items"
        :key="item.conversation_id"
        data-testid="queue-item"
        class="queue-item"
        :class="{ 'queue-item--unread': queue.unreadIds.includes(item.conversation_id) }"
      >
        <span
          data-testid="queue-item-badge"
          class="badge"
          :data-variant="item.customer_id !== null ? 'primary' : 'neutral'"
        >
          {{ item.customer_id !== null ? '客户' : '访客' }}
        </span>
        <div class="queue-item__body">
          <p class="queue-item__title">{{ item.last_user_message ?? '转接会话' }}</p>
          <p class="queue-item__meta">
            {{ handoffReasonLabel(item.reason) }} · {{ waitLabel(item.created_at) }}
          </p>
        </div>
        <button
          data-testid="queue-accept-btn"
          class="btn btn--primary btn--sm"
          type="button"
          @click="accept(item.conversation_id)"
        >
          接入
        </button>
      </div>
    </div>

    <!-- 空状态（PRD §queue 变体段「空状态」：居中 §5 empty-state 插画 + 主辅文案） -->
    <div
      v-if="!queue.loading && queue.items.length === 0"
      data-testid="queue-empty"
      class="empty-state"
    >
      <div
        data-testid="queue-empty-illustration"
        class="empty-state__illustration"
        aria-hidden="true"
      />
      <p class="empty-state__title">暂无待接入会话</p>
      <p class="empty-state__hint">有新转接会话将在此显示</p>
    </div>

    <!-- 回呼请求分组（离线兜底，US-29；数据源 GET /agents/callbacks） -->
    <div
      v-if="!queue.loading && queue.callbacks.length > 0"
      data-testid="queue-callback-group"
      class="callback-group"
    >
      <p class="callback-group__title">回呼请求</p>
      <div
        v-for="cb in queue.callbacks"
        :key="cb.ticket_id"
        data-testid="queue-callback-item"
        class="queue-item"
      >
        <span data-testid="queue-callback-phone" class="queue-item__title">{{
          cb.customer_phone
        }}</span>
        <div class="queue-item__body">
          <p class="queue-item__meta">离线兜底回呼</p>
        </div>
        <button
          data-testid="queue-callback-call-btn"
          class="btn btn--outline btn--sm"
          type="button"
        >
          拨打
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 页面容器：内容区背景 surface-base，内边距 24px（PRD §queue）。 */
.queue-page {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 统计条：白底 shadow-xs 圆角 8px 卡片（DESIGN.md §5 卡片容器）。 */
.stats-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
  border-radius: 8px;
  padding: 16px;
}

.stats-card__left {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.stats-card__count {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.stats-card__hint {
  font-size: 12px;
  color: #6b7280;
}

/* 全忙线变体：辅助文案 semantic-warning 700（PRD §queue 全部忙线变体）。 */
.stats-card__hint--warning {
  color: #f57f17;
}

/* 刷新图标按钮（DESIGN.md §5 图标按钮：32×32 线性图标）。 */
.icon-btn--refresh {
  position: relative;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
}

.icon-btn--refresh::before {
  content: '';
  position: absolute;
  inset: 0;
  margin: auto;
  width: 14px;
  height: 14px;
  border: 1.5px solid #4b5563;
  border-top-color: transparent;
  border-radius: 50%;
}

.icon-btn--refresh:hover {
  background: #f3f4f6;
}

/* 待接入列表 + 回呼分组共用列表行（56px 宽松，DESIGN.md §5 列表行）。 */
.queue-item {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 56px;
  background: #ffffff;
  border-bottom: 1px solid #f3f4f6;
  padding: 12px 16px;
}

/* 新进入项未读高亮：semantic-info-tint-bg #E8F4FB，无色条（PRD 状态策略 Handoff 等待）。 */
.queue-item--unread {
  background: #e8f4fb;
}

.queue-item__body {
  flex: 1;
  min-width: 0;
}

.queue-item__title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.queue-item__meta {
  margin: 2px 0 0;
  font-size: 12px;
  color: #6b7280;
}

/* 客户标识徽章（DESIGN.md §5 状态徽章：圆角 4px、Caption 12px）。 */
.badge {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  line-height: 16px;
}

.badge[data-variant='primary'] {
  background: #e0ebff;
  color: #0a47b8;
}

.badge[data-variant='neutral'] {
  background: #f3f4f6;
  color: #374151;
}

/* 按钮（DESIGN.md §5.1）：主按钮 28px 小号 / 描边按钮（Primary 500 文字）。 */
.btn {
  flex-shrink: 0;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
}

.btn--sm {
  height: 28px;
  padding: 0 12px;
  font-size: 13px;
}

.btn--primary {
  background: #1a6fff;
  color: #ffffff;
}

.btn--primary:hover {
  background: #0d5be6;
}

.btn--outline {
  background: transparent;
  color: #1a6fff;
  border: 1px solid transparent;
}

.btn--outline:hover {
  background: #f4f8ff;
  border-color: #1a6fff;
}

/* 骨架屏（DESIGN.md §5.10）：Neutral 100 底 + Neutral 200 高光，列表行骨架。 */
.skeleton-list {
  display: flex;
  flex-direction: column;
}

.skeleton-item {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 56px;
  background: #ffffff;
  border-bottom: 1px solid #f3f4f6;
  padding: 12px 16px;
}

.skeleton-item__badge {
  width: 40px;
  height: 16px;
  border-radius: 4px;
  background: #f3f4f6;
}

.skeleton-item__lines {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skeleton-item__line {
  height: 12px;
  border-radius: 4px;
  background: #f3f4f6;
}

.skeleton-item__line--long {
  width: 60%;
}

.skeleton-item__line--short {
  width: 30%;
}

/* 空状态（DESIGN.md §5.9）：垂直水平居中，插画 64px 线性 Neutral 300。 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
}

.empty-state__illustration {
  width: 64px;
  height: 64px;
  border-radius: 8px;
  border: 1.5px dashed #d1d5db;
  background:
    linear-gradient(#ffffff, #ffffff) padding-box,
    linear-gradient(#ffffff, #ffffff) border-box;
  margin-bottom: 12px;
}

.empty-state__title {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: #374151;
}

.empty-state__hint {
  margin: 8px 0 0;
  font-size: 13px;
  color: #6b7280;
}

/* 回呼请求分组（PRD §queue：列表底部独立分组，标题 Caption 12px Neutral 500）。 */
.callback-group {
  margin-top: 8px;
}

.callback-group__title {
  margin: 0 0 4px;
  padding: 0 16px;
  font-size: 12px;
  color: #6b7280;
}
</style>
