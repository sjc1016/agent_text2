<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'

import { listMessages, type ChatMessage } from '../api/conversations'
import { useSessionStore } from '../stores/session'

/**
 * customer-web 历史会话只读视图（PRD §profile 会话历史段「点击进入历史会话只读视图」；#11）。
 *
 * 继承 app-shell（底栏 Tab 保持「我的」），顶部返回按钮回 /profile。
 * 只读语义：仅拉取会话消息历史（GET /conversations/{id}/messages，B2）静态展示，
 * 无输入区、无 WS、无操作入口（US-17「回顾既往交互」）。
 */

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const conversationId = Number(route.params.id)
const messages = ref<ChatMessage[]>([])
const loading = ref(true)

onMounted(async () => {
  if (!session.isAuthenticated) {
    loading.value = false
    return
  }
  try {
    messages.value = await listMessages(session.accessToken, conversationId)
  } catch {
    // 会话不存在 / 非本人（404）：保持空列表，展示「暂无消息」（不泄露存在性）
  } finally {
    loading.value = false
  }
})

/** 消息来源 → 气泡修饰类（user/assistant/agent/system 四类，同 ChatView 规格）。 */
function bubbleClass(source: string): string {
  return `bubble--${source}`
}
</script>

<template>
  <div data-testid="profile-history-view" class="profile-history-view">
    <!-- 顶栏：返回按钮 + 标题（PRD §profile 会话历史只读视图） -->
    <header class="history-header">
      <button
        data-testid="history-back"
        class="history-back"
        type="button"
        aria-label="返回"
        @click="router.push('/profile')"
      >
        <el-icon :size="20"><ArrowLeft /></el-icon>
      </button>
      <h1 data-testid="history-title" class="history-title">历史会话</h1>
    </header>

    <!-- 加载变体：消息列表骨架屏（DESIGN.md §5.10；States 矩阵 loading 语义） -->
    <div v-if="loading" data-testid="history-skeleton" class="history-skeleton" aria-busy="true">
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

    <!-- 消息历史（只读）：四类气泡同 ChatView 规格 -->
    <div v-else-if="messages.length > 0" data-testid="history-messages" class="history-messages">
      <div
        v-for="message in messages"
        :key="message.id"
        data-testid="message-bubble"
        :data-source="message.source"
        class="bubble"
        :class="bubbleClass(message.source)"
      >
        <span v-if="message.source === 'agent'" data-testid="agent-tag" class="bubble__agent-tag"
          >坐席</span
        >
        {{ message.content }}
      </div>
    </div>

    <!-- 空态：会话无消息（或无权访问） -->
    <div v-else data-testid="history-empty" class="history-empty">
      <p class="history-empty__text">暂无消息</p>
    </div>
  </div>
</template>

<style scoped>
.profile-history-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f9fafb; /* surface-base Neutral 50 */
}

/* 顶栏：返回图标按钮 + 标题（DESIGN.md §5.6 顶栏；PRD §profile 只读视图）。 */
.history-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 24px 0;
}

.history-back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #4b5563; /* Neutral 600 */
  cursor: pointer;
}

.history-back:hover {
  background: #f3f4f6; /* Neutral 100 */
  color: #1f2937;
}

/* 标题：H1 20px(600) Neutral 800（DESIGN.md §3 字号阶梯）。 */
.history-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  line-height: 28px;
  color: #1f2937;
}

/* 消息历史流：可滚动、内边距 16px（同 ChatView 对话流规格）。 */
.history-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 气泡（DESIGN.md §5 卡片：助理/坐席左对齐白气泡，用户右对齐 Primary）。 */
.bubble {
  max-width: 70%;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 14px;
  line-height: 20px;
  color: #1f2937; /* Neutral 800 */
  white-space: pre-wrap;
  word-break: break-word;
}

.bubble--assistant {
  align-self: flex-start;
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.06); /* shadow-xs */
  border-top-left-radius: 0; /* 左上角直角 */
}

.bubble--user {
  align-self: flex-end;
  background: #1a6fff; /* Primary 500 */
  color: #ffffff;
  border-top-right-radius: 0; /* 右上角直角 */
}

.bubble--agent {
  align-self: flex-start;
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.06);
  border-top-left-radius: 0;
}

/* 坐席标识：与助理同形，左侧小标签区分（PRD chat 坐席消息）。 */
.bubble__agent-tag {
  display: inline-block;
  margin-right: 6px;
  padding: 0 6px;
  border-radius: 4px;
  background: #e0ebff; /* primary-tint-bg-strong */
  color: #0a47b8; /* Primary 700 */
  font-size: 12px;
  line-height: 18px;
}

/* 系统消息：无气泡，整行 info tint 底居中（PRD chat 系统消息规格）。 */
.bubble--system {
  align-self: center;
  max-width: none;
  background: #e8f4fb; /* semantic-info-tint-bg */
  color: #01579b; /* semantic-info 700 */
  font-size: 12px;
  line-height: 18px;
  border-radius: 4px;
  padding: 4px 8px;
}

/* 骨架屏：48px 行左头像圆形 + 右两行文本条（DESIGN.md §5.10）。 */
.history-skeleton {
  flex: 1;
  padding: 16px;
}

.history-skeleton-item {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 48px;
  padding: 8px 0;
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

/* 空态：无消息时居中（状态策略「无匹配结果」风格 14px Neutral 400）。 */
.history-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
}

.history-empty__text {
  margin: 0;
  font-size: 14px;
  color: #9ca3af; /* Neutral 400 */
}
</style>
