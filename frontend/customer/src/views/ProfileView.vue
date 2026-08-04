<script setup lang="ts">
/**
 * customer-web「我的」页（PRD 页面清单 §profile；issue #11 UI-C-5）。
 *
 * 继承 customer-web app-shell，底栏 Tab 选中「我的」（路由 /profile，壳层定义）。
 * 内容区（PRD）：顶部账号卡片（头像占位 + 号码脱敏 + 状态徽章 + 套餐简述）+
 * 会话历史区块（起止时间 + 末条消息预览 + Closed 徽章，点击进入只读视图）+
 * 底部退出登录反色按钮。
 * 数据源：profile store（history/loading/planSummary）+ session store（认证态）。
 */
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Clock } from '@element-plus/icons-vue'

import { useProfileStore, type ConversationHistoryItem } from '../stores/profile'
import { useSessionStore } from '../stores/session'
import { useChatStore } from '../stores/chat'

const store = useProfileStore()
const session = useSessionStore()
const chat = useChatStore()
const router = useRouter()

onMounted(() => {
  if (session.isAuthenticated) store.load(session.accessToken)
})

/** 头像占位首字母：号码脱敏首字符（PRD 头像占位 40×40 圆形 + 首字母）。 */
const avatarInitial = computed(() => session.maskedPhone.slice(0, 1) || '访')

/** ISO → `YYYY-MM-DD HH:mm`（起止时间展示，保持本地无关的确定格式）。 */
function formatDateTime(iso: string): string {
  return iso.slice(0, 16).replace('T', ' ')
}

/** 会话起止时间：起（会话创建）~ 止（末条消息时间）。 */
function timeRange(item: ConversationHistoryItem): string {
  const start = formatDateTime(item.startedAt)
  const end = item.endedAt ? formatDateTime(item.endedAt) : ''
  return end ? `${start} ~ ${end}` : start
}

/** 点击会话历史行 → 只读视图（US-17）。 */
function openHistory(conversationId: number) {
  router.push(`/profile/history/${conversationId}`)
}

/** 退出登录（US-17）：清除认证与会话数据，返回访客态。 */
function logout() {
  session.logout()
  chat.logout()
}
</script>

<template>
  <div data-testid="profile-view" class="profile-view">
    <h1 data-testid="profile-title" class="profile-title">我的</h1>

    <!-- 账号卡片：圆角 8px shadow-xs 白底内边距 16px（PRD §profile 顶部账号卡片段；DESIGN.md §5.3） -->
    <section data-testid="account-card" class="account-card">
      <div data-testid="account-avatar" class="account-card__avatar">{{ avatarInitial }}</div>
      <div class="account-card__body">
        <!-- 已认证：号码脱敏 H3 16px Neutral 800 + Primary 徽章 + 套餐简述 -->
        <template v-if="session.isAuthenticated">
          <p data-testid="account-phone" class="account-card__phone">{{ session.maskedPhone }}</p>
          <span data-testid="account-status-badge" class="badge badge--primary">已认证</span>
          <p data-testid="account-plan" class="account-card__plan">{{ store.planSummary }}</p>
        </template>
        <!-- 访客空状态（States 矩阵 visitor-empty）：「访客身份」+ 主按钮「去认证」 -->
        <template v-else>
          <p data-testid="account-guest-name" class="account-card__phone">访客身份</p>
          <button
            data-testid="go-auth-button"
            class="btn btn--primary btn--sm"
            type="button"
            @click="router.push('/auth')"
          >
            去认证
          </button>
        </template>
      </div>
    </section>

    <!-- 会话历史：区块标题 H2 18px + 列表行 48px（PRD §profile 会话历史段） -->
    <template v-if="session.isAuthenticated">
      <h2 data-testid="history-title" class="history-title">会话历史</h2>

      <!-- 加载变体（States 矩阵 loading / DESIGN.md §5.10 骨架屏）：48px 行左头像圆形 + 右两行文本条 -->
      <div
        v-if="store.loading"
        data-testid="history-skeleton"
        class="history-skeleton"
        aria-busy="true"
      >
        <div
          v-for="n in 3"
          :key="n"
          data-testid="history-skeleton-item"
          class="history-skeleton-item"
        >
          <div class="history-skeleton-item__avatar" />
          <div class="history-skeleton-item__lines">
            <div class="history-skeleton-item__line history-skeleton-item__line--long" />
            <div class="history-skeleton-item__line history-skeleton-item__line--short" />
          </div>
        </div>
      </div>

      <div
        v-if="!store.loading && store.history.length > 0"
        data-testid="history-list"
        class="history-list"
      >
        <button
          v-for="item in store.history"
          :key="item.id"
          data-testid="history-row"
          class="history-row"
          type="button"
          @click="openHistory(item.id)"
        >
          <div class="history-row__body">
            <p data-testid="history-row-time" class="history-row__time">{{ timeRange(item) }}</p>
            <p data-testid="history-row-preview" class="history-row__preview">
              {{ item.preview || '（无消息）' }}
            </p>
          </div>
          <!-- Closed → Neutral 徽章（States 矩阵 default：状态徽章 Closed→Neutral） -->
          <span
            v-if="item.status === 'closed'"
            data-testid="history-status-badge"
            data-variant="neutral"
            class="badge badge--neutral"
            >已结束</span
          >
        </button>
      </div>
      <!-- 会话历史空状态（States 矩阵 history-empty）：居中插画 + 主文案「暂无历史会话」 -->
      <div v-else-if="!store.loading" data-testid="history-empty" class="empty-state">
        <el-icon
          data-testid="history-empty-illustration"
          :size="64"
          class="empty-state__illustration"
          aria-hidden="true"
        >
          <Clock />
        </el-icon>
        <p class="empty-state__title">暂无历史会话</p>
      </div>
    </template>

    <!-- 底部退出登录反色按钮：白底 Primary 600 文字，置于浅底（PRD §profile 底部固定区） -->
    <div v-if="session.isAuthenticated" class="profile-footer">
      <button data-testid="logout-button" class="btn btn--inverted" type="button" @click="logout">
        退出登录
      </button>
    </div>
  </div>
</template>

<style scoped>
/* surface-base 底 + 24px 内边距（PRD §profile 内容区；DESIGN.md §2 surface-base）。 */
.profile-view {
  padding: 24px;
  background: #f9fafb;
}

/* 页面标题：H1 20px(600) Neutral 800（PRD §profile 顶栏标题段；DESIGN.md §3 字号阶梯）。 */
.profile-title {
  margin: 0 0 16px;
  font-size: 20px;
  font-weight: 600;
  line-height: 28px;
  color: #1f2937;
}

/* 账号卡片：圆角 8px shadow-xs 白底、内边距 16px（DESIGN.md §5.3 卡片容器）。 */
.account-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: #ffffff;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04); /* shadow-xs */
}

/* 头像占位：40×40 圆形 primary-tint-bg-strong 底 + 首字母 Primary 700（PRD §profile）。 */
.account-card__avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #e0ebff; /* primary-tint-bg-strong */
  color: #0a47b8; /* Primary 700 */
  font-size: 16px;
  font-weight: 600;
  flex-shrink: 0;
}

.account-card__body {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  min-width: 0;
}

/* 号码脱敏：H3 16px(600) Neutral 800（PRD §profile 账号卡片段）。 */
.account-card__phone {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
  color: #1f2937;
}

/* 套餐简述：Body-sm 13px(400) Neutral 500（PRD §profile 账号卡片段）。 */
.account-card__plan {
  margin: 0;
  font-size: 13px;
  line-height: 20px;
  color: #6b7280;
}

/* 会话历史区块标题：H2 18px(600) Neutral 800、间距下 12px（PRD §profile）。 */
.history-title {
  margin: 16px 0 12px;
  font-size: 18px;
  font-weight: 600;
  line-height: 26px;
  color: #1f2937;
}

/* 历史列表：白底列表行（DESIGN.md §5.4 列表行：48px、底部分隔 Neutral 100）。 */
.history-list {
  background: #ffffff;
  border-radius: 8px;
  overflow: hidden;
}

.history-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 48px;
  padding: 8px 16px;
  background: #ffffff;
  border: none;
  border-bottom: 1px solid #f3f4f6; /* Neutral 100 */
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.history-row:last-child {
  border-bottom: none;
}

.history-row:hover {
  background: #f4f8ff; /* primary-tint-bg（DESIGN.md §5.4 悬停） */
}

/* 骨架屏：48px 行左头像圆形 + 右两行文本条（DESIGN.md §5.10；States 矩阵 loading）。 */
.history-skeleton {
  background: #ffffff;
  border-radius: 8px;
  overflow: hidden;
}

.history-skeleton-item {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 48px;
  padding: 8px 16px;
  border-bottom: 1px solid #f3f4f6; /* Neutral 100 */
}

.history-skeleton-item:last-child {
  border-bottom: none;
}

.history-skeleton-item__avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #f3f4f6; /* Neutral 100 */
  flex-shrink: 0;
}

.history-skeleton-item__lines {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.history-skeleton-item__line {
  height: 12px;
  border-radius: 4px;
  background: linear-gradient(90deg, #f3f4f6 25%, #e5e7eb 37%, #f3f4f6 63%);
  background-size: 400% 100%;
  animation: skeleton-scan 1.5s ease-in-out infinite;
}

.history-skeleton-item__line--long {
  width: 60%;
}

.history-skeleton-item__line--short {
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

.history-row__body {
  flex: 1;
  min-width: 0;
}

/* 起止时间：Caption 12px(500) Neutral 500（PRD §profile 会话历史段）。 */
.history-row__time {
  margin: 0;
  font-size: 12px;
  font-weight: 500;
  line-height: 18px;
  color: #6b7280;
}

/* 末条消息预览：Body-sm 13px(400) Neutral 500 截断（CSS ellipsis，PRD §profile）。 */
.history-row__preview {
  margin: 2px 0 0;
  font-size: 13px;
  line-height: 20px;
  color: #6b7280;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 状态徽章：DESIGN.md §5.7 形态（圆角 4px、内边距 2×8、12px/500）。 */
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

.badge--primary {
  background: #e0ebff; /* primary-tint-bg-strong */
  color: #0a47b8; /* Primary 700 */
}

.badge--neutral {
  background: #f3f4f6; /* Neutral 100 */
  color: #374151; /* Neutral 700 */
}

/* 底部固定区退出按钮（PRD §profile 底部固定区，间距上 24px）。 */
.profile-footer {
  margin-top: 24px;
  display: flex;
  justify-content: center;
}

/* 主按钮（小号）：Primary 500 底白字、圆角 6px（DESIGN.md §5.1；访客「去认证」）。 */
.btn--primary {
  background: #1a6fff;
  color: #ffffff;
  font-size: 13px;
  font-weight: 500;
}

.btn--primary:hover {
  background: #0d5be6; /* Primary 600 */
}

.btn--sm {
  padding: 6px 14px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-family: inherit;
}

/* 空状态：居中、内边距 48×24（DESIGN.md §5.9；会话历史空状态）。 */
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

/* 主文案：14px(500) Neutral 700 居中（DESIGN.md §5.9）。 */
.empty-state__title {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  line-height: 22px;
  color: #374151;
}

/* 反色按钮：白底 Primary 600 文字、圆角 6px、悬停 Neutral 100（DESIGN.md §5.1 Inverted）。 */
.btn--inverted {
  padding: 0 24px;
  height: 36px;
  border: none;
  border-radius: 6px;
  background: #ffffff;
  color: #0d5be6; /* Primary 600 */
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}

.btn--inverted:hover {
  background: #f3f4f6; /* Neutral 100 */
}
</style>
