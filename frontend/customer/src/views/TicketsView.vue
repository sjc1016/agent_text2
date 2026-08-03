<script setup lang="ts">
/**
 * customer-web「我的工单」页（PRD 页面清单 §tickets；issue #16 UI-C-4）。
 *
 * 继承 customer-web app-shell，底栏 Tab 选中「我的工单」（路由 /tickets，壳层定义）。
 * 内容区（PRD）：顶部通知预览条（未读 Notification）+ 工单列表（类型图标 + 主文案 +
 * 创建时间 + 状态徽章，点击行展开内联嵌套卡片：详情 + 状态流转时间线 + 关联通知）。
 * 数据源：tickets store（tickets/notifications/loading/expandedId）。
 */
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Document, Tickets } from '@element-plus/icons-vue'

import { ticketBadgeVariant, ticketStatusLabel, ticketTypeLabel } from '../api/tickets'
import { useTicketsStore } from '../stores/tickets'
import { useSessionStore } from '../stores/session'

const store = useTicketsStore()
const session = useSessionStore()
const router = useRouter()

onMounted(() => {
  if (session.isAuthenticated) store.load(session.accessToken)
})

/** 工单类型图标（办理类/工单类区分，PRD §tickets 列表段）。 */
function typeIcon(ticketType: string) {
  return ticketType === 'ticketing' ? Document : Tickets
}

/** 创建时间展示（ISO → YYYY-MM-DD）。 */
function timeLabel(createdAt: string): string {
  return createdAt.slice(0, 10)
}
</script>

<template>
  <div data-testid="tickets-view" class="tickets-view">
    <h1 data-testid="tickets-title" class="tickets-title">我的工单</h1>

    <!-- 通知预览条（若有未读 Notification）：整宽 semantic-info-tint-bg 卡片，点击跳转对应工单
         （PRD §tickets 顶部通知预览条段；DESIGN.md §4 semantic-info-tint-bg） -->
    <div
      v-if="session.isAuthenticated && !store.loading && store.unreadNotifications.length > 0"
      data-testid="notice-preview-bar"
      class="notice-preview-bar"
    >
      <button
        v-for="n in store.unreadNotifications"
        :key="n.id"
        data-testid="notice-preview-item"
        class="notice-preview-item"
        type="button"
        @click="store.expandTicket(n.ticket_id)"
      >
        <span class="notice-preview-item__message">{{ n.message }}</span>
        <span class="notice-preview-item__time">{{ timeLabel(n.created_at) }}</span>
      </button>
    </div>

    <!-- 未认证变体（PRD §tickets 变体段「未认证变体」：空状态主文案 + 主按钮「去认证」跳 auth） -->
    <div v-if="!session.isAuthenticated" data-testid="tickets-unauthenticated" class="empty-state">
      <el-icon :size="64" class="empty-state__illustration" aria-hidden="true">
        <Tickets />
      </el-icon>
      <p class="empty-state__title">请先认证查看工单</p>
      <button
        data-testid="go-auth-button"
        class="btn btn--primary"
        type="button"
        @click="router.push('/auth')"
      >
        去认证
      </button>
    </div>

    <!-- 加载变体（PRD §tickets 变体段「加载变体」/ DESIGN.md §5.10 骨架屏）：列表骨架屏 56px 行左图标 + 右两行文本条 -->
    <div
      v-if="session.isAuthenticated && store.loading"
      data-testid="tickets-skeleton"
      class="skeleton-list"
      aria-busy="true"
    >
      <div v-for="n in 3" :key="n" data-testid="skeleton-item" class="skeleton-item">
        <div class="skeleton-item__icon" />
        <div class="skeleton-item__lines">
          <div class="skeleton-item__line skeleton-item__line--long" />
          <div class="skeleton-item__line skeleton-item__line--short" />
        </div>
      </div>
    </div>

    <!-- 工单列表（可滚动；每行 56px 宽松，PRD §tickets 列表段） -->
    <div
      v-if="session.isAuthenticated && !store.loading && store.tickets.length > 0"
      data-testid="tickets-list"
      class="tickets-list"
    >
      <div v-for="t in store.tickets" :key="t.id" class="ticket-group">
        <div
          data-testid="ticket-row"
          class="ticket-row"
          role="button"
          tabindex="0"
          @click="store.toggleExpand(t.id)"
        >
          <el-icon :size="16" class="ticket-row__icon" aria-hidden="true">
            <component :is="typeIcon(t.ticket_type)" />
          </el-icon>
          <div class="ticket-row__body">
            <p class="ticket-row__title">{{ ticketTypeLabel(t.ticket_type) }} · {{ t.content }}</p>
            <p class="ticket-row__meta">{{ timeLabel(t.created_at) }}</p>
          </div>
          <span
            data-testid="ticket-status-badge"
            class="badge"
            :data-variant="ticketBadgeVariant(t)"
            :class="`badge--${ticketBadgeVariant(t)}`"
            >{{ ticketStatusLabel(t) }}</span
          >
        </div>

        <!-- 展开的内联嵌套卡片：Neutral 50 底 6px 圆角无阴影（PRD §tickets 点击展开段；DESIGN.md §5.3 嵌套卡片） -->
        <div
          v-if="store.expandedId === t.id"
          data-testid="ticket-detail-card"
          class="ticket-detail-card"
        >
          <section class="nested-section">
            <h3 class="nested-section__title">工单详情</h3>
            <p class="nested-section__content">{{ t.content }}</p>
          </section>

          <section class="nested-section">
            <h3 class="nested-section__title">状态流转时间线</h3>
            <!-- 时间线节点：已创建（created_at）+ 当前状态（后端无状态历史，仅当前态；数据缺口待后端补） -->
            <ol class="timeline">
              <li class="timeline__item">
                <span class="timeline__node" aria-hidden="true" />
                <span class="timeline__label">已创建</span>
                <span class="timeline__time">{{ timeLabel(t.created_at) }}</span>
              </li>
              <li class="timeline__item">
                <span class="timeline__node" aria-hidden="true" />
                <span class="timeline__label">{{ ticketStatusLabel(t) }}</span>
              </li>
            </ol>
          </section>

          <section v-if="store.notificationsFor(t.id).length > 0" class="nested-section">
            <h3 class="nested-section__title">关联通知</h3>
            <ul class="notice-list">
              <li v-for="n in store.notificationsFor(t.id)" :key="n.id" class="notice-list__item">
                {{ n.message }}
              </li>
            </ul>
          </section>
        </div>
      </div>
    </div>

    <!-- 空状态（PRD §tickets 变体段「空状态」：居中 §5 empty-state 插画 + 主辅文案） -->
    <div
      v-if="session.isAuthenticated && !store.loading && store.tickets.length === 0"
      data-testid="tickets-empty"
      class="empty-state"
    >
      <el-icon
        data-testid="tickets-empty-illustration"
        :size="64"
        class="empty-state__illustration"
        aria-hidden="true"
      >
        <Tickets />
      </el-icon>
      <p class="empty-state__title">暂无工单</p>
      <p class="empty-state__hint">办理业务或报修后将在此显示</p>
    </div>
  </div>
</template>

<style scoped>
/* surface-base 底 + 24px 内边距（PRD §tickets 内容区；DESIGN.md §2 surface-base）。 */
.tickets-view {
  padding: 24px;
  background: #f9fafb;
}

/* 页面标题：H1 20px(600) Neutral 800（PRD §tickets 顶栏标题段；DESIGN.md §3 字号阶梯）。 */
.tickets-title {
  margin: 0 0 16px;
  font-size: 20px;
  font-weight: 600;
  line-height: 28px;
  color: #1f2937;
}

/* 通知预览条：semantic-info-tint-bg 底圆角 8px（PRD §tickets 顶部预览条段；DESIGN.md §4）。 */
.notice-preview-bar {
  margin-bottom: 16px;
  background: #e8f4fb;
  border-radius: 8px;
  padding: 4px 12px;
}

.notice-preview-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 6px 0;
  border: none;
  background: transparent;
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.notice-preview-item__message {
  font-size: 12px;
  font-weight: 500;
  line-height: 18px;
  color: #01579b;
}

.notice-preview-item__time {
  font-size: 12px;
  line-height: 18px;
  color: #6b7280;
  flex-shrink: 0;
}

/* 列表行：56px 宽松、白底、底部分隔线 Neutral 100、内边距 12×16（DESIGN.md §5.4 列表行）。 */
.ticket-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 56px;
  padding: 12px 16px;
  background: #ffffff;
  border-bottom: 1px solid #f3f4f6;
}

.ticket-row__icon {
  color: #4b5563;
  flex-shrink: 0;
}

.ticket-row__body {
  flex: 1;
  min-width: 0;
}

/* 主文案：H3 16px(600) Neutral 800（PRD §tickets 列表段）。 */
.ticket-row__title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 辅助文案：Caption 12px(500) Neutral 500（PRD §tickets 列表段）。 */
.ticket-row__meta {
  margin: 2px 0 0;
  font-size: 12px;
  font-weight: 500;
  line-height: 18px;
  color: #6b7280;
}

/* 状态徽章：DESIGN.md §5.7 形态（圆角 4px、内边距 2×8、12px/500）+ 五变体映射。 */
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  line-height: 16px;
  flex-shrink: 0;
}

/* §5.7 变体：Neutral（已取消/回退）/ Warning（待执行/待派单）/ Info（执行中/处理中）/
   Success（已生效/已关闭）/ Error（已失败）。 */
.badge--neutral {
  background: #f3f4f6;
  color: #374151;
}

.badge--warning {
  background: #fff6e0;
  color: #f57f17;
}

.badge--info {
  background: #e8f4fb;
  color: #01579b;
}

.badge--success {
  background: #ebf5ec;
  color: #1b5e20;
}

.badge--error {
  background: #fceaea;
  color: #b71c1c;
}

/* 内联嵌套卡片：Neutral 50 底、6px 圆角、无阴影（DESIGN.md §5.3 嵌套卡片规则）。 */
.ticket-detail-card {
  margin: 0 16px;
  padding: 12px 16px;
  background: #f9fafb;
  border-radius: 6px;
}

.nested-section + .nested-section {
  margin-top: 12px;
}

.nested-section__title {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 500;
  line-height: 18px;
  color: #6b7280;
}

.nested-section__content {
  margin: 0;
  font-size: 13px;
  line-height: 20px;
  color: #1f2937;
}

/* 时间线（展开卡片）：纵向节点 + 状态标签。 */
.timeline {
  margin: 0;
  padding: 0;
  list-style: none;
}

.timeline__item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 22px;
}

.timeline__node {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #9ca3af;
  flex-shrink: 0;
}

.timeline__label {
  font-size: 13px;
  line-height: 20px;
  color: #1f2937;
}

.timeline__time {
  font-size: 12px;
  color: #6b7280;
}

/* 关联通知列表。 */
.notice-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.notice-list__item {
  font-size: 13px;
  line-height: 20px;
  color: #1f2937;
}

/* 骨架屏列表：56px 行、Neutral 100 底、Neutral 200 高光扫描（DESIGN.md §5.10）。 */
.skeleton-list {
  background: #ffffff;
}

.skeleton-item {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 56px;
  padding: 12px 16px;
  border-bottom: 1px solid #f3f4f6;
}

.skeleton-item__icon {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  background: #f3f4f6;
  flex-shrink: 0;
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
  background: linear-gradient(90deg, #f3f4f6 25%, #e5e7eb 37%, #f3f4f6 63%);
  background-size: 400% 100%;
  animation: skeleton-scan 1.5s ease-in-out infinite;
}

.skeleton-item__line--long {
  width: 60%;
}

.skeleton-item__line--short {
  width: 30%;
}

@keyframes skeleton-scan {
  0% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0 50%;
  }
}

/* 空状态：居中、内边距 48×24（DESIGN.md §5.9）。 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  text-align: center;
}

/* 插画：64px 线性 Neutral 300（DESIGN.md §5.9）。 */
.empty-state__illustration {
  color: #d1d5db;
  margin-bottom: 16px;
}

/* 主文案：14px(500) Neutral 700；辅助：13px(400) Neutral 500 间距 8px（DESIGN.md §5.9）。 */
.empty-state__title {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  line-height: 22px;
  color: #374151;
}

.empty-state__hint {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 20px;
  color: #6b7280;
}

/* 主按钮：Primary 500 底白字、圆角 6px、36px（DESIGN.md §5.1；每屏最多 1 个）。 */
.btn--primary {
  margin-top: 16px;
  padding: 0 20px;
  height: 36px;
  border: none;
  border-radius: 6px;
  background: #1a6fff;
  color: #ffffff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.btn--primary:hover {
  background: #0d5be6;
}
</style>
