<script setup lang="ts">
/**
 * 进行中会话页（US-21/22/23/25/26，issue #21）。
 *
 * 继承 agent-console app-shell，侧栏选中「进行中」（路由 /active-chat）。
 * 规格：PRD 页面清单 §active-chat「UI 设计描述」+ 变体段；DESIGN.md §5 气泡/按钮/状态徽章/骨架屏。
 * 数据源：REST 真契约（B12 #44 / B14 #55，见 api/activeChat.ts 契约清单）；
 * 坐席 WS（take_over/message/state_transition）走后端 B9 真契约。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Close, Promotion } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { AgentWsClient } from '../api/agentWs'
import {
  createAgentTicket,
  executeAgentTicket,
  fetchAgentConversation,
  fetchAgentCustomerProfile,
  handoffReasonLabel,
  listAgentMessages,
  listAgentTickets,
  ticketStatusLabel,
  type AgentChatMessage,
  type AgentConversationView,
  type AgentCustomerProfile,
  type AgentTicket,
} from '../api/activeChat'
import type { MessageNewPayload, WsEvent } from 'shared/events'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

/** 会话 ID：路由 query `conversation_id`（QueueView 接入时携带）。 */
const conversationId = computed<number | null>(() => {
  const n = Number(route.query.conversation_id)
  return Number.isInteger(n) && n > 0 ? n : null
})

const conversation = ref<AgentConversationView | null>(null)
const messages = ref<AgentChatMessage[]>([])
const profile = ref<AgentCustomerProfile | null>(null)
const tickets = ref<AgentTicket[]>([])
const loading = ref(false)
/** 客户资料加载中（PRD 加载变体：头像圆形 + 两行文本条骨架屏）。 */
const profileLoading = ref(false)

/** 空状态：无进行中会话（无会话 ID 或会话不存在）→ 居中 empty-state + 前往待接入队列。 */
const empty = computed(() => !loading.value && conversation.value === null)

/** 输入区草稿（发送后清空）。 */
const draft = ref('')
const canSend = computed(() => draft.value.trim() !== '')

/** 坐席发消息（US-22）：WS sendMessage 出站，坐席自身消息由后端 message.new 回显。 */
function send() {
  const content = draft.value.trim()
  if (!content || conversationId.value === null) return
  ws?.sendMessage(conversationId.value, content)
  draft.value = ''
}

/** 创建工单 Modal（US-23）：工单类型 Select + 内容 textarea + 主按钮「创建」。 */
const showCreateModal = ref(false)
const newTicketType = ref<'transaction' | 'ticketing'>('transaction')
const newTicketContent = ref('')
const creating = ref(false)
const createError = ref('')

function openCreateModal() {
  showCreateModal.value = true
  newTicketType.value = 'transaction'
  newTicketContent.value = ''
  createError.value = ''
}

function closeCreateModal() {
  if (creating.value) return
  showCreateModal.value = false
}

async function submitCreateTicket() {
  const content = newTicketContent.value.trim()
  if (!content || creating.value || conversationId.value === null) return
  creating.value = true
  createError.value = ''
  try {
    const ticket = await createAgentTicket(
      conversationId.value,
      { ticket_type: newTicketType.value, content },
      auth.accessToken,
    )
    tickets.value.push(ticket)
    showCreateModal.value = false
  } catch (err) {
    createError.value = err instanceof Error ? err.message : '创建工单失败，请重试'
  } finally {
    creating.value = false
  }
}

/** 服务密码复核 Modal（US-25）：待执行办理工单执行前，坐席引导用户再次输入服务密码。 */
const executingTicket = ref<AgentTicket | null>(null)
const reauthPassword = ref('')
const reauthing = ref(false)
const reauthError = ref('')

function openReauth(ticket: AgentTicket) {
  executingTicket.value = ticket
  reauthPassword.value = ''
  reauthError.value = ''
}

function closeReauth() {
  if (reauthing.value) return
  executingTicket.value = null
}

async function submitReauth() {
  const password = reauthPassword.value.trim()
  if (!password || reauthing.value || executingTicket.value === null) return
  if (conversationId.value === null) return
  reauthing.value = true
  reauthError.value = ''
  try {
    await executeAgentTicket(
      conversationId.value,
      executingTicket.value.id,
      password,
      auth.accessToken,
    )
    reauthPassword.value = ''
    executingTicket.value = null
  } catch (err) {
    reauthError.value = err instanceof Error ? err.message : '执行失败，请重试'
  } finally {
    reauthing.value = false
  }
}

let ws: AgentWsClient | null = null

/** WS 事件处理：message.new 追加到对话流（含坐席自身发送后的回显）。 */
function handleWsEvent(event: WsEvent) {
  if (event.event === 'message.new') {
    // WsEvent 为泛型接口（event/data 非可判别联合），收窄需显式断言（同 customer chat store 模式）
    const data = event.data as MessageNewPayload
    if (
      data.conversation_id === conversationId.value &&
      !messages.value.some((m) => m.id === data.id)
    ) {
      messages.value.push(data)
    }
  }
}

/** 接入会话：WS 打开后发送 take_over（US-21，绑定坐席到 handed_off 会话）。 */
function sendTakeOver() {
  if (conversationId.value !== null) ws?.sendTakeOver(conversationId.value)
}

/** 转回助理（US-26）：WS state_transition 出站（handed_off → authenticated），跳回 queue。 */
function transferBack() {
  if (conversationId.value === null) return
  ws?.sendStateTransition(conversationId.value)
  router.push({ name: 'queue' })
}

function initWs() {
  ws = new AgentWsClient({
    getToken: () => auth.accessToken,
    onEvent: handleWsEvent,
    onOpen: sendTakeOver,
  })
  ws.connect()
}

async function loadData() {
  const id = conversationId.value
  if (id === null) return
  loading.value = true
  try {
    conversation.value = await fetchAgentConversation(id, auth.accessToken)
    if (conversation.value === null) return
    messages.value = await listAgentMessages(id, auth.accessToken)
    profileLoading.value = true
    try {
      // 访客会话（无 Customer）无客户资料端点：本地构造访客卡（联系方式自会话头）；
      // 认证客户 → GET /agents/customers/{customer_id}（B12 AC2）。
      const customerId = conversation.value.customer_id
      profile.value =
        customerId === null
          ? {
              customer_id: null,
              phone: conversation.value.customer_phone,
              name: null,
              authenticated: false,
              contact_name: null,
              contact_phone: null,
              account_balance: null,
              plan_name: null,
              contract_expiry: null,
            }
          : await fetchAgentCustomerProfile(customerId, auth.accessToken)
    } finally {
      profileLoading.value = false
    }
    tickets.value = await listAgentTickets(id, auth.accessToken)
  } finally {
    loading.value = false
    profileLoading.value = false
  }
}

onMounted(() => {
  if (conversationId.value === null) return
  void loadData()
  initWs()
})

onUnmounted(() => {
  ws?.close()
  ws = null
})

/** 消息来源 → 气泡修饰类（四类 + 助理草稿，对应 §5 气泡样式）。 */
function bubbleClass(source: AgentChatMessage['source']): string {
  return `bubble--${source}`
}

/** 待执行办理工单（transaction + pending）才显示「执行」按钮（US-25）。 */
function canExecute(t: AgentTicket): boolean {
  return t.ticket_type === 'transaction' && t.status === 'pending'
}

function ticketBadgeVariant(t: AgentTicket): string {
  return t.ticket_type === 'transaction' ? 'primary' : 'neutral'
}
</script>

<template>
  <div data-testid="active-chat-view" class="active-chat">
    <!-- 顶栏：当前会话标题（号码脱敏）+「转回助理」描边按钮（PRD §active-chat 顶栏） -->
    <header data-testid="active-chat-header" class="active-chat__header">
      <h3 data-testid="active-chat-title" class="active-chat__title">
        {{ conversation?.customer_phone ?? '进行中会话' }}
      </h3>
      <button
        data-testid="active-chat-transfer-btn"
        class="btn btn--outline"
        type="button"
        @click="transferBack"
      >
        转回助理
      </button>
    </header>

    <!-- 空状态：无进行中会话居中 empty-state + 主按钮「前往待接入队列」（PRD §active-chat 空状态变体） -->
    <div v-if="empty" data-testid="active-chat-empty" class="active-chat__empty">
      <div class="empty-state__illustration" aria-hidden="true" />
      <p class="empty-state__title">暂无进行中会话</p>
      <p class="empty-state__hint">有新的待接入会话时将出现在这里</p>
      <button
        data-testid="go-queue-btn"
        class="btn btn--primary"
        type="button"
        @click="router.push({ name: 'queue' })"
      >
        前往待接入队列
      </button>
    </div>

    <!-- 内容区左右两栏：左对话区 flex 填充约 65%，右客户资料侧栏约 35%（不对称留白左密右疏） -->
    <div v-else class="active-chat__body">
      <!-- 左对话区：对话流 + 底部输入区（PRD §active-chat 左栏） -->
      <section data-testid="chat-pane" class="chat-pane">
        <div data-testid="chat-messages" class="chat-messages">
          <div
            v-for="m in messages"
            :key="m.id"
            data-testid="message-bubble"
            :data-source="m.source"
            class="bubble"
            :class="bubbleClass(m.source)"
          >
            <span v-if="m.source === 'agent'" data-testid="agent-tag" class="bubble__agent-tag"
              >坐席</span
            >
            <span
              v-else-if="m.source === 'assistant_draft'"
              data-testid="draft-tag"
              class="bubble__draft-tag"
              >草稿</span
            >
            {{ m.content }}
          </div>
        </div>

        <!-- 输入区：固定底白底 1px Neutral 100 顶分隔，textarea + 发送主色图标按钮 -->
        <div class="chat-input">
          <div class="chat-input__toolbar">
            <button
              data-testid="create-ticket-btn"
              class="btn btn--text"
              type="button"
              @click="openCreateModal"
            >
              创建工单
            </button>
          </div>
          <textarea
            v-model="draft"
            data-testid="chat-textarea"
            class="chat-input__textarea"
            rows="2"
            placeholder="回复客户…"
          />
          <button
            data-testid="chat-send"
            class="chat-input__send"
            type="button"
            aria-label="发送"
            :disabled="!canSend"
            @click="send"
          >
            <el-icon :size="18"><Promotion /></el-icon>
          </button>
        </div>
      </section>

      <!-- 右客户资料侧栏：白底 shadow-xs 圆角 8px，内边距 16px（PRD §active-chat 右栏） -->
      <aside data-testid="customer-pane" class="customer-pane">
        <!-- 加载变体：客户资料骨架屏（头像圆形 + 两行文本条） -->
        <div
          v-if="profileLoading"
          data-testid="profile-skeleton"
          class="profile-skeleton"
          aria-busy="true"
        >
          <div class="profile-skeleton__avatar" />
          <div class="profile-skeleton__line profile-skeleton__line--long" />
          <div class="profile-skeleton__line profile-skeleton__line--short" />
        </div>

        <template v-else-if="profile">
          <!-- 客户标识卡：头像 + 号码脱敏 + 状态徽章（已认证/访客） -->
          <div data-testid="customer-profile-card" class="profile-card">
            <div data-testid="profile-avatar" class="profile-card__avatar" aria-hidden="true" />
            <div class="profile-card__body">
              <p data-testid="profile-phone" class="profile-card__phone">{{ profile.phone }}</p>
              <span
                data-testid="profile-status-badge"
                class="badge"
                :data-variant="profile.authenticated ? 'primary' : 'neutral'"
              >
                {{ profile.authenticated ? '已认证' : '访客' }}
              </span>
            </div>
          </div>

          <!-- 访客变体：仅记录联系方式（PRD 变体段「访客变体」，无账户信息） -->
          <template v-if="!profile.authenticated">
            <p data-testid="visitor-hint" class="visitor-hint">访客身份，仅记录联系方式</p>
            <div data-testid="contact-card" class="nested-card">
              <h4 class="nested-card__title">联系方式</h4>
              <dl class="nested-card__rows">
                <div class="nested-card__row">
                  <dt class="nested-card__label">联系人</dt>
                  <dd data-testid="contact-name" class="nested-card__value">
                    {{ profile.contact_name ?? '未提供' }}
                  </dd>
                </div>
                <div class="nested-card__row">
                  <dt class="nested-card__label">联系电话</dt>
                  <dd data-testid="contact-phone" class="nested-card__value">
                    {{ profile.contact_phone ?? '未提供' }}
                  </dd>
                </div>
              </dl>
            </div>
          </template>

          <!-- 账户信息嵌套卡片：话费余额 Primary 700 + 套餐名 + 合约到期（认证客户专属） -->
          <div v-if="profile.authenticated" data-testid="account-card" class="nested-card">
            <h4 class="nested-card__title">账户信息</h4>
            <dl class="nested-card__rows">
              <div class="nested-card__row">
                <dt class="nested-card__label">话费余额</dt>
                <dd
                  data-testid="account-balance"
                  class="nested-card__value nested-card__value--primary"
                >
                  {{ profile.account_balance }}
                </dd>
              </div>
              <div class="nested-card__row">
                <dt class="nested-card__label">套餐</dt>
                <dd data-testid="account-plan" class="nested-card__value">
                  {{ profile.plan_name }}
                </dd>
              </div>
              <div class="nested-card__row">
                <dt class="nested-card__label">合约到期</dt>
                <dd data-testid="account-expiry" class="nested-card__value">
                  {{ profile.contract_expiry }}
                </dd>
              </div>
            </dl>
          </div>

          <!-- 当前工单嵌套卡片：36px 紧凑列表行，工单类型 + 状态徽章 -->
          <div data-testid="ticket-card" class="nested-card">
            <h4 class="nested-card__title">当前工单</h4>
            <div v-for="t in tickets" :key="t.id" data-testid="ticket-item" class="ticket-item">
              <div class="ticket-item__body">
                <p class="ticket-item__content">{{ t.content }}</p>
                <span
                  data-testid="ticket-item-badge"
                  class="badge"
                  :data-variant="ticketBadgeVariant(t)"
                >
                  {{ ticketStatusLabel(t) }}
                </span>
              </div>
              <button
                v-if="canExecute(t)"
                data-testid="ticket-execute-btn"
                class="btn btn--primary btn--sm"
                type="button"
                @click="openReauth(t)"
              >
                执行
              </button>
            </div>
          </div>

          <!-- 转接上下文嵌套卡片：转接原因 + 助理已尝试操作摘要 -->
          <div data-testid="handoff-context-card" class="nested-card">
            <h4 class="nested-card__title">转接上下文</h4>
            <p data-testid="handoff-reason" class="nested-card__text">
              {{ handoffReasonLabel(conversation?.handoff_reason ?? null) }}
            </p>
            <ul data-testid="handoff-attempts" class="nested-card__list">
              <li v-for="(a, i) in conversation?.assistant_attempts ?? []" :key="i">{{ a }}</li>
            </ul>
          </div>
        </template>
      </aside>
    </div>

    <!-- 创建工单 Modal（US-23，同二次确认 Modal 规格：工单类型 Select + 内容 textarea + 主按钮「创建」） -->
    <div v-if="showCreateModal" data-testid="create-ticket-modal" class="modal-overlay">
      <div class="modal" role="dialog" aria-modal="true" aria-label="创建工单">
        <header class="modal__header">
          <h3 class="modal__title">创建工单</h3>
          <button
            type="button"
            class="modal__close"
            data-testid="create-ticket-close"
            aria-label="关闭"
            @click="closeCreateModal"
          >
            <el-icon :size="16"><Close /></el-icon>
          </button>
        </header>

        <div class="modal__body">
          <label class="modal-field">
            <span class="modal-field__label">工单类型</span>
            <select v-model="newTicketType" data-testid="ticket-type-select" class="modal-input">
              <option value="transaction">办理类</option>
              <option value="ticketing">工单类</option>
            </select>
          </label>
          <label class="modal-field">
            <span class="modal-field__label">内容</span>
            <textarea
              v-model="newTicketContent"
              data-testid="ticket-content"
              class="modal-input modal-input--textarea"
              rows="3"
              placeholder="请输入工单内容"
            />
          </label>
          <p v-if="createError" data-testid="create-ticket-error" class="modal-error">
            {{ createError }}
          </p>
        </div>

        <footer class="modal__footer">
          <button
            type="button"
            class="btn btn--outline"
            data-testid="create-ticket-cancel"
            @click="closeCreateModal"
          >
            取消
          </button>
          <button
            type="button"
            class="btn btn--primary btn--lg"
            data-testid="create-ticket-submit"
            :disabled="!newTicketContent.trim() || creating"
            @click="submitCreateTicket"
          >
            {{ creating ? '创建中…' : '创建' }}
          </button>
        </footer>
      </div>
    </div>

    <!-- 服务密码复核 Modal（US-25，同 customer-web 规格：坐席引导用户再次输入服务密码） -->
    <div v-if="executingTicket" data-testid="reauth-modal" class="modal-overlay">
      <div class="modal" role="dialog" aria-modal="true" aria-label="服务密码复核">
        <header class="modal__header">
          <h3 class="modal__title">服务密码复核</h3>
          <button
            type="button"
            class="modal__close"
            data-testid="reauth-close"
            aria-label="关闭"
            @click="closeReauth"
          >
            <el-icon :size="16"><Close /></el-icon>
          </button>
        </header>

        <div class="modal__body">
          <!-- 复核提示：semantic-warning-tint-bg 强调底（DESIGN.md §5.3 警告语义） -->
          <p data-testid="reauth-message" class="reauth-banner">
            执行「{{ executingTicket.content }}」需进行服务密码复核，请引导用户输入服务密码
          </p>
          <input
            v-model="reauthPassword"
            data-testid="reauth-password"
            class="modal-input"
            type="password"
            autocomplete="current-password"
            placeholder="请输入服务密码"
          />
          <p v-if="reauthError" data-testid="reauth-error" class="modal-error">{{ reauthError }}</p>
        </div>

        <footer class="modal__footer">
          <button
            type="button"
            class="btn btn--text"
            data-testid="reauth-cancel"
            @click="closeReauth"
          >
            取消
          </button>
          <button
            type="button"
            class="btn btn--primary btn--lg"
            data-testid="reauth-submit"
            :disabled="!reauthPassword.trim() || reauthing"
            @click="submitReauth"
          >
            {{ reauthing ? '执行中…' : '确认执行' }}
          </button>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ---- 布局：顶栏 + 左右两栏（不对称留白左密右疏，PRD §active-chat）---- */
.active-chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f9fafb; /* surface-base Neutral 50 */
}

.active-chat__header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: #ffffff;
  border-bottom: 1px solid #f3f4f6; /* Neutral 100 */
}

.active-chat__title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1f2937; /* Neutral 800 */
}

.active-chat__body {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* 空状态（DESIGN.md §5.9 + PRD 空状态变体）：垂直水平居中，插画 + 主文案 + 主按钮 */
.active-chat__empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
}

.active-chat__empty .empty-state__illustration {
  width: 64px;
  height: 64px;
  border-radius: 8px;
  border: 1.5px dashed #d1d5db; /* Neutral 300 */
  background:
    linear-gradient(#ffffff, #ffffff) padding-box,
    linear-gradient(#ffffff, #ffffff) border-box;
  margin-bottom: 12px;
}

.active-chat__empty .empty-state__title {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  color: #374151; /* Neutral 700 */
}

.active-chat__empty .empty-state__hint {
  margin: 8px 0 16px;
  font-size: 13px;
  color: #6b7280; /* Neutral 500 */
}

/* 左对话区：flex 填充约 65%，背景 surface-base，内边距 16px */
.chat-pane {
  flex: 1.85;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 输入区：固定底，白底 + 1px Neutral 100 顶分隔 */
.chat-input {
  flex-shrink: 0;
  background: #ffffff;
  border-top: 1px solid #f3f4f6;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chat-input__toolbar {
  display: flex;
  align-items: center;
}

.chat-input__textarea {
  width: 100%;
  min-height: 56px;
  border: 1px solid #d1d5db; /* Neutral 300 */
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 14px;
  line-height: 20px;
  color: #1f2937;
  resize: none;
  box-sizing: border-box;
  font-family: inherit;
}

.chat-input__textarea:focus {
  outline: none;
  border-color: #1a6fff;
  box-shadow: 0 0 0 2px #c9deff; /* shadow-focus */
}

.chat-input__send {
  align-self: flex-end;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 6px;
  background: #1a6fff; /* Primary 500 */
  color: #ffffff;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.chat-input__send:disabled {
  background: #9dbdff; /* Primary 300（禁用态） */
  cursor: not-allowed;
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
  border-top-left-radius: 0;
}

.bubble--user {
  align-self: flex-end;
  background: #1a6fff;
  color: #ffffff;
  border-top-right-radius: 0;
}

.bubble--agent {
  align-self: flex-start;
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.06);
  border-top-left-radius: 0;
}

/* 助理草稿：tertiary-tint-bg 底区分（PRD §active-chat 对话区段，后台起草仅坐席可见） */
.bubble--assistant_draft {
  align-self: flex-start;
  background: #fff1e5; /* tertiary-tint-bg */
  border-top-left-radius: 0;
}

/* 草稿标识：与坐席标签同形，tertiary 语义色区分 */
.bubble__draft-tag {
  display: inline-block;
  margin-right: 6px;
  padding: 0 6px;
  border-radius: 4px;
  background: #ffd9b3; /* tertiary-tint-bg-strong */
  color: #c2410c; /* tertiary 700 */
  font-size: 12px;
  line-height: 18px;
}

/* 坐席标识：与助理同形，左侧小标签区分（PRD §active-chat 坐席消息，用户视角仍是「客服」） */
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

/* 系统消息：无气泡，整行 info tint 底居中 */
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

/* ---- 右客户资料侧栏：白底 shadow-xs 圆角 8px，内边距 16px，可滚动 ---- */
.customer-pane {
  flex: 1;
  min-width: 280px;
  background: #ffffff;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04); /* shadow-xs */
  border-radius: 8px;
  margin: 16px;
  padding: 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 客户标识卡：头像 + 号码脱敏 + 状态徽章 */
.profile-card {
  display: flex;
  align-items: center;
  gap: 12px;
}

.profile-card__avatar {
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: #e0ebff; /* primary-tint-bg-strong */
}

.profile-card__body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.profile-card__phone {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

/* 访客提示：semantic-warning-tint-bg 强调底（PRD 变体段「访客变体」） */
.visitor-hint {
  margin: 0;
  padding: 8px 12px;
  border-radius: 8px;
  background: #fff6e0; /* semantic-warning-tint-bg */
  color: #f57f17; /* semantic-warning 700 */
  font-size: 13px;
  line-height: 20px;
}

/* 状态徽章（DESIGN.md §5：圆角 4px、Caption 12px） */
.badge {
  align-self: flex-start;
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

/* 嵌套卡片：Neutral 50 底圆角 6px 无阴影（PRD §active-chat 分块嵌套卡片） */
.nested-card {
  background: #f9fafb; /* Neutral 50 */
  border-radius: 6px;
  padding: 12px;
}

.nested-card__title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #374151; /* Neutral 700 */
}

.nested-card__rows {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.nested-card__row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.nested-card__label {
  flex-shrink: 0;
  font-size: 13px;
  color: #6b7280; /* Neutral 500 */
}

.nested-card__value {
  margin: 0;
  font-size: 13px;
  color: #374151;
  text-align: right;
}

.nested-card__value--primary {
  font-size: 16px;
  font-weight: 600;
  color: #0a47b8; /* Primary 700 */
}

.nested-card__text {
  margin: 0;
  font-size: 13px;
  color: #6b7280;
}

.nested-card__list {
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 13px;
  color: #6b7280;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* 当前工单：36px 紧凑列表行（DESIGN.md §5 列表行紧凑） */
.ticket-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding: 4px 0;
}

.ticket-item__body {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.ticket-item__content {
  margin: 0;
  font-size: 13px;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 按钮（DESIGN.md §5.1）：主按钮 28px 小号 / 描边按钮 / 文字按钮 */
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

.btn--text {
  height: 28px;
  padding: 0 8px;
  background: transparent;
  color: #1a6fff;
  font-size: 13px;
}

.btn--text:hover {
  background: #f4f8ff;
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
  color: #6b7280;
  cursor: pointer;
}

.modal__close:hover {
  background: #f3f4f6;
  color: #1f2937;
}

.modal__body {
  padding-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.modal__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #f3f4f6; /* Neutral 100 */
}

/* 表单字段：Label 13px Neutral 500 + 输入控件 */
.modal-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.modal-field__label {
  font-size: 13px;
  color: #6b7280; /* Neutral 500 */
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
  font-family: inherit;
}

.modal-input--textarea {
  height: auto;
  resize: none;
}

.modal-input::placeholder {
  color: #9ca3af; /* Neutral 400 */
}

.modal-input:focus {
  outline: none;
  border-color: transparent;
  box-shadow: 0 0 0 2px #c9deff; /* shadow-focus（Primary 100） */
}

/* Modal 内错误文案：semantic-error 500 */
.modal-error {
  margin: 0;
  font-size: 12px;
  font-weight: 500;
  color: #e53935; /* semantic-error 500 */
}

/* 复核提示条：semantic-warning-tint-bg 强调底 + warning 700 文字（§5.3 警告语义） */
.reauth-banner {
  margin: 0;
  padding: 8px 12px;
  border-radius: 8px;
  background: #fff6e0; /* semantic-warning-tint-bg */
  color: #f57f17; /* semantic-warning 700 */
  font-size: 13px;
  line-height: 20px;
}

/* 客户资料骨架屏（DESIGN.md §5.10）：头像圆形 + 两行文本条 */
.profile-skeleton {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}

.profile-skeleton__avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: #f3f4f6; /* Neutral 100 */
}

.profile-skeleton__line {
  height: 12px;
  border-radius: 4px;
  background: #f3f4f6;
}

.profile-skeleton__line--long {
  width: 60%;
}

.profile-skeleton__line--short {
  width: 30%;
}
</style>
