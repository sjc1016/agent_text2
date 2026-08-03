<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { CircleCloseFilled, Close, Promotion } from '@element-plus/icons-vue'

import { useChatStore } from '../stores/chat'
import { useSessionStore } from '../stores/session'

/**
 * customer-web 主会话页（PRD 页面清单 §chat；#24 UI-C-3 集成切片）。
 *
 * 内容区上下两段：
 *   - 对话流区：四类消息（助理/用户/坐席/系统）+ 空状态问候 + 助理生成信号脉冲
 *     + 发送失败重发 + Handoff 等待脉冲 + 二次确认 Modal + 服务密码复核 Modal。
 *   - 输入区：textarea（回车发送、Shift+回车换行）+ 发送主色图标按钮。
 * 数据源：chat store（conversationId/messages/assistantPending/failedContent/
 *   pendingConfirm/pendingReauth…）。
 */

const chat = useChatStore()
const session = useSessionStore()
const router = useRouter()

const draft = ref('')
const messagesEl = ref<HTMLElement | null>(null)

/** 二次确认 / 复核提交中（防重复提交）+ Modal inline 错误文案（States 矩阵 error 语义）。 */
const confirming = ref(false)
const reauthing = ref(false)
const reauthPassword = ref('')
const confirmError = ref('')
const reauthError = ref('')

/** 输入禁用：访客未认证（无法建会话/连 WS）或 Handed-off 转接中（States 矩阵 disabled）。 */
const inputDisabled = computed(() => !session.isAuthenticated || chat.isHandedOff)

const canSend = computed(() => !inputDisabled.value && draft.value.trim() !== '')

function send() {
  const content = draft.value.trim()
  if (!content || !canSend.value) return
  chat.sendMessage(content)
  draft.value = ''
}

function retry() {
  chat.retrySend()
}

/** 消息来源 → 气泡修饰类（user/assistant/agent/system 四类，对应 §5 气泡样式）。 */
function bubbleClass(source: string): string {
  return `bubble--${source}`
}

/** 确认办理：POST /transactions/confirm 入队（失败 Modal 内错误文案，保持打开）。 */
async function onConfirm() {
  if (!chat.pendingConfirm || confirming.value) return
  confirming.value = true
  confirmError.value = ''
  try {
    await chat.confirmPending()
  } catch (err) {
    confirmError.value = err instanceof Error ? err.message : '确认办理失败，请重试'
  } finally {
    confirming.value = false
  }
}

/** 复核并执行：/auth/reauth → execute_token → /transactions/{id}/execute（失败保留输入）。 */
async function onReauth() {
  if (!chat.pendingReauth || reauthing.value) return
  reauthing.value = true
  reauthError.value = ''
  try {
    await chat.reauthAndExecute(reauthPassword.value)
    reauthPassword.value = ''
  } catch (err) {
    reauthError.value = err instanceof Error ? err.message : '执行失败，请重试'
  } finally {
    reauthing.value = false
  }
}

/** 新消息/流式文本到达时滚动到底部。 */
watch(
  () => [chat.messages.length, chat.assistantPartial] as const,
  async () => {
    await nextTick()
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  },
)

onMounted(() => {
  chat.init()
})

onUnmounted(() => {
  chat.disconnect()
})
</script>

<template>
  <div data-testid="chat-view" class="chat-view">
    <!-- 上方对话流区：flex 填充可滚动，背景 surface-base，内边距 16px -->
    <div ref="messagesEl" data-testid="chat-messages" class="chat-messages">
      <!-- 访客（未认证）：认证引导（无法建会话/连 WS，PRD 访客升格路径 US-2） -->
      <div v-if="!session.isAuthenticated" data-testid="guest-hint" class="guest-hint">
        <span class="guest-hint__text">请先认证后开始对话</span>
        <button
          type="button"
          class="btn btn--primary btn--sm"
          data-testid="go-auth-button"
          @click="router.push('/auth')"
        >
          去认证
        </button>
      </div>

      <!-- 空状态：新会话助理先发问候气泡（States 矩阵 empty） -->
      <div v-if="chat.showGreeting" data-testid="greeting-bubble" class="bubble bubble--assistant">
        您好，我是电信客服助理，请问有什么可以帮您？
      </div>

      <!-- 四类消息气泡（States 矩阵 default） -->
      <div
        v-for="message in chat.messages"
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

      <!-- 助理生成中：信号脉冲 3 圆点 + 累积文本（States 矩阵 loading） -->
      <div
        v-if="chat.assistantPending"
        data-testid="assistant-loading"
        class="bubble bubble--assistant"
      >
        <span class="signal-pulse" aria-hidden="true">
          <i v-for="n in 3" :key="n" class="signal-pulse__dot" />
        </span>
        <span v-if="chat.assistantPartial" class="assistant-loading__text">{{
          chat.assistantPartial
        }}</span>
      </div>

      <!-- Handoff 等待：坐席接入前信号脉冲（States 矩阵 handoff-waiting） -->
      <div
        v-if="chat.isHandedOff"
        data-testid="handoff-pulse"
        class="handoff-pulse"
        aria-label="正在为您转接坐席"
      >
        <span class="signal-pulse" aria-hidden="true">
          <i v-for="n in 3" :key="n" class="signal-pulse__dot" />
        </span>
      </div>

      <!-- 发送失败：用户气泡 + Error 图标 + 重发（States 矩阵 error） -->
      <div v-if="chat.failedContent !== null" data-testid="failed-bubble" class="failed-bubble">
        <button type="button" class="btn btn--text" data-testid="retry-button" @click="retry">
          重发
        </button>
        <div class="bubble bubble--user bubble--failed">
          <span data-testid="failed-error-icon" class="bubble__failed-icon">
            <el-icon :size="16" aria-label="发送失败"><CircleCloseFilled /></el-icon>
          </span>
          {{ chat.failedContent }}
        </div>
      </div>
    </div>

    <!-- 下方输入区：固定底部，白底 + 顶分隔线，内边距 12×16 -->
    <div class="chat-input">
      <textarea
        v-model="draft"
        data-testid="chat-textarea"
        class="chat-input__textarea"
        :disabled="inputDisabled"
        :placeholder="chat.isHandedOff ? '正在为您转接坐席…' : '请描述您的问题…'"
        rows="2"
        @keydown.enter.exact.prevent="send"
      />
      <button
        type="button"
        data-testid="chat-send"
        class="chat-input__send"
        :disabled="!canSend"
        aria-label="发送"
        @click="send"
      >
        <el-icon :size="18"><Promotion /></el-icon>
      </button>
    </div>

    <!-- 二次确认 Modal（States 矩阵 second-confirm-modal）：办理发起后弹出（US-8~US-11） -->
    <div v-if="chat.pendingConfirm" data-testid="second-confirm-modal" class="modal-overlay">
      <div class="modal" role="dialog" aria-modal="true" aria-label="确认办理">
        <header class="modal__header">
          <h3 class="modal__title">确认办理</h3>
          <button
            type="button"
            class="modal__close"
            data-testid="confirm-close"
            aria-label="关闭"
            @click="chat.cancelConfirm()"
          >
            <el-icon :size="16"><Close /></el-icon>
          </button>
        </header>

        <div class="modal__body">
          <p data-testid="confirm-summary" class="confirm-summary">
            {{ chat.pendingConfirm.business_impact.summary }}
          </p>
          <!-- 结构化业务影响嵌套卡片：Neutral 50 底、无描边分区；费用变化 tertiary-tint-bg 强调 -->
          <dl data-testid="impact-card" class="impact-card">
            <div class="impact-card__row">
              <dt class="impact-card__label">套餐对比</dt>
              <dd class="impact-card__value">
                {{ chat.pendingConfirm.business_impact.plan_comparison }}
              </dd>
            </div>
            <div class="impact-card__row">
              <dt class="impact-card__label">生效时间</dt>
              <dd class="impact-card__value">
                {{ chat.pendingConfirm.business_impact.effective_time }}
              </dd>
            </div>
            <div class="impact-card__row">
              <dt class="impact-card__label">合约影响</dt>
              <dd class="impact-card__value">
                {{ chat.pendingConfirm.business_impact.contract_impact }}
              </dd>
            </div>
            <div class="impact-card__row impact-card__row--fee">
              <dt class="impact-card__label">费用变化</dt>
              <dd class="impact-card__value">
                {{ chat.pendingConfirm.business_impact.fee_change }}
              </dd>
            </div>
          </dl>
          <p v-if="confirmError" data-testid="confirm-error" class="modal-error">
            {{ confirmError }}
          </p>
        </div>

        <footer class="modal__footer">
          <button
            type="button"
            class="btn btn--outline"
            data-testid="confirm-cancel"
            @click="chat.cancelConfirm()"
          >
            取消
          </button>
          <button
            type="button"
            class="btn btn--primary btn--lg"
            data-testid="confirm-submit"
            :disabled="confirming"
            @click="onConfirm"
          >
            {{ confirming ? '提交中…' : '确认办理' }}
          </button>
        </footer>
      </div>
    </div>

    <!-- 服务密码复核 Modal（States 矩阵 reauth-modal）：执行前弹出（US-12） -->
    <div v-if="chat.pendingReauth" data-testid="reauth-modal" class="modal-overlay">
      <div class="modal" role="dialog" aria-modal="true" aria-label="服务密码复核">
        <header class="modal__header">
          <h3 class="modal__title">服务密码复核</h3>
          <button
            type="button"
            class="modal__close"
            data-testid="reauth-close"
            aria-label="关闭"
            @click="chat.cancelReauth()"
          >
            <el-icon :size="16"><Close /></el-icon>
          </button>
        </header>

        <div class="modal__body">
          <!-- 复核提示：semantic-warning-tint-bg 强调底（DESIGN.md §5.3 警告语义） -->
          <p data-testid="reauth-message" class="reauth-banner">{{ chat.pendingReauth.message }}</p>
          <input
            v-model="reauthPassword"
            data-testid="reauth-password"
            class="modal-input"
            type="password"
            autocomplete="current-password"
            placeholder="请输入服务密码"
            @keydown.enter.prevent="onReauth"
          />
          <p v-if="reauthError" data-testid="reauth-error" class="modal-error">{{ reauthError }}</p>
        </div>

        <footer class="modal__footer">
          <button
            type="button"
            class="btn btn--text"
            data-testid="reauth-cancel"
            @click="chat.cancelReauth()"
          >
            取消
          </button>
          <button
            type="button"
            class="btn btn--primary btn--lg"
            data-testid="reauth-submit"
            :disabled="!reauthPassword || reauthing"
            @click="onReauth"
          >
            {{ reauthing ? '执行中…' : '确认执行' }}
          </button>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ---- 布局：上下两段 ---- */
.chat-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f9fafb; /* surface-base Neutral 50 */
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-input {
  flex-shrink: 0;
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 12px 16px;
  background: #ffffff;
  border-top: 1px solid #f3f4f6; /* Neutral 100 */
}

/* ---- 气泡（DESIGN.md §5 卡片：助理/坐席左对齐白气泡，用户右对齐 Primary）---- */
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

/* 坐席标识：与助理同形，左侧小标签区分（PRD chat 坐席消息） */
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

/* 系统消息：无气泡，整行 info tint 底居中（PRD chat 系统消息规格） */
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

/* 发送失败气泡：Error 图标置气泡右上角 */
.bubble--failed {
  position: relative;
  padding-right: 28px;
}

.bubble__failed-icon {
  position: absolute;
  top: -6px;
  right: -6px;
  color: #b71c1c; /* semantic-error 500 */
  background: #ffffff;
  border-radius: 50%;
}

.failed-bubble {
  align-self: flex-end;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

/* ---- 信号脉冲（DESIGN.md §5：3 圆点 Primary 500，1.4s 脉动、0.2s 延迟递进）---- */
.signal-pulse {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

.signal-pulse__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #1a6fff; /* Primary 500 */
  animation: signal-pulse 1.4s ease-in-out infinite;
}

.signal-pulse__dot:nth-child(2) {
  animation-delay: 0.2s;
}

.signal-pulse__dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes signal-pulse {
  0%,
  100% {
    opacity: 0.35;
    transform: scale(0.85);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}

.assistant-loading {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.handoff-pulse {
  align-self: flex-start;
  padding: 8px 12px;
}

/* ---- 输入区 ---- */
.chat-input__textarea {
  flex: 1;
  resize: none;
  border: 1px solid #d1d5db; /* Neutral 300 */
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 14px;
  line-height: 20px;
  font-family: inherit;
  color: #1f2937;
  background: #ffffff;
}

.chat-input__textarea:focus {
  outline: none;
  box-shadow: 0 0 0 3px rgba(26, 111, 255, 0.18); /* shadow-focus */
  border-color: transparent;
}

.chat-input__textarea:disabled {
  background: #f3f4f6; /* Neutral 100 */
  color: #9ca3af; /* Neutral 400 */
}

.chat-input__send {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: #1a6fff; /* Primary 500 */
  color: #ffffff;
  cursor: pointer;
  flex-shrink: 0;
}

.chat-input__send:disabled {
  background: #e5e7eb; /* Neutral 200（DESIGN.md §5 主按钮禁用态） */
  cursor: not-allowed;
}

/* ---- 访客认证引导 ---- */
.guest-hint {
  display: flex;
  align-items: center;
  gap: 12px;
  align-self: center;
  background: #f3f4f6; /* Neutral 100 */
  border-radius: 8px;
  padding: 8px 16px;
}

.guest-hint__text {
  font-size: 13px;
  color: #6b7280; /* Neutral 500 */
}

/* ---- 通用按钮（DESIGN.md §5：主/文字按钮小号） ---- */
.btn {
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-family: inherit;
}

.btn--primary {
  background: #1a6fff;
  color: #ffffff;
  font-size: 13px;
  font-weight: 500;
}

.btn--sm {
  padding: 6px 14px;
}

.btn--text {
  background: transparent;
  color: #1a6fff; /* Primary 500 */
  font-size: 13px;
  padding: 2px 4px;
}

/* ---- Modal 弹层（DESIGN.md §5.3：圆角 12px / shadow-lg / 24px 内边距） ---- */
.modal-overlay {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(8, 12, 20, 0.5); /* neutral-overlay（Neutral 900 @ 50%） */
  z-index: 100;
}

.modal {
  width: 400px;
  max-width: calc(100vw - 32px);
  border-radius: 12px;
  background: #ffffff;
  box-shadow:
    0 10px 15px rgba(0, 0, 0, 0.1),
    0 4px 6px rgba(0, 0, 0, 0.05); /* shadow-lg */
  padding: 24px;
}

/* Header 与 Body 间极淡分区线（1px Neutral 100，§6 无描边规则） */
.modal__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 1px solid #f3f4f6; /* Neutral 100 */
}

.modal__title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1f2937; /* Neutral 800 */
}

.modal__close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #6b7280; /* Neutral 500 */
  cursor: pointer;
}

.modal__close:hover {
  background: #f3f4f6;
  color: #1f2937;
}

.modal__body {
  padding-top: 16px;
}

.modal__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #f3f4f6; /* Neutral 100 */
}

/* ---- 二次确认 Modal ---- */
.confirm-summary {
  margin: 0 0 12px;
  font-size: 14px;
  line-height: 20px;
  color: #1f2937;
}

/* 结构化业务影响嵌套卡片：Neutral 50 底、无描边分区（§5.3 嵌套卡片） */
.impact-card {
  margin: 0;
  padding: 4px 16px;
  border-radius: 8px;
  background: #f9fafb; /* Neutral 50 */
}

.impact-card__row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  padding: 6px 0;
}

/* 关键费用：tertiary-tint-bg 强调底（Tertiary 500 @ 10%），同 §4 叠色规则 */
.impact-card__row--fee {
  margin: 4px -16px;
  padding: 6px 16px;
  background: #fff1e5; /* tertiary-tint-bg */
}

.impact-card__label {
  flex-shrink: 0;
  font-size: 13px;
  color: #6b7280; /* Neutral 500 */
}

.impact-card__value {
  margin: 0;
  text-align: right;
  font-size: 13px;
  font-weight: 500;
  color: #1f2937; /* Neutral 800 */
}

/* ---- 复核 Modal ---- */
/* 复核提示条：semantic-warning-tint-bg 强调底 + warning 700 文字（§5.3 警告语义） */
.reauth-banner {
  margin: 0 0 16px;
  padding: 8px 12px;
  border-radius: 8px;
  background: #fff6e0; /* semantic-warning-tint-bg */
  color: #f57f17; /* semantic-warning 700 */
  font-size: 13px;
  line-height: 20px;
}

.modal-input {
  width: 100%;
  height: 36px;
  padding: 8px 12px;
  border: 1px solid #d1d5db; /* Neutral 300 */
  border-radius: 6px;
  background: #ffffff;
  font-size: 14px;
  color: #1f2937;
  box-sizing: border-box;
}

.modal-input::placeholder {
  color: #9ca3af; /* Neutral 400 */
}

.modal-input:focus {
  outline: none;
  border-color: transparent;
  box-shadow: 0 0 0 2px #c9deff; /* shadow-focus（Primary 100） */
}

/* Modal 内错误文案：semantic-error 500（§5.2 错误态） */
.modal-error {
  margin: 8px 0 0;
  font-size: 12px;
  font-weight: 500;
  color: #e53935; /* semantic-error 500 */
}

/* ---- 描边按钮（DESIGN.md §5.1 Outline：白底 + Primary 500 描边/文字） ---- */
.btn--outline {
  background: #ffffff;
  color: #1a6fff;
  font-size: 14px;
  font-weight: 500;
  border: 1px solid #1a6fff; /* Primary 500 */
}

.btn--lg {
  height: 40px;
  padding: 0 20px;
  font-size: 14px;
}

.btn--primary.btn--lg:disabled {
  background: #e5e7eb; /* Neutral 200 */
  color: #9ca3af; /* Neutral 400 */
  cursor: not-allowed;
}
</style>
