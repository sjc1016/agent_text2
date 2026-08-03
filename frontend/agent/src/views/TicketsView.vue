<script setup lang="ts">
/**
 * agent-console「工单管理」页（PRD 页面清单 §tickets(agent-console)；issue #22 UI-A-5）。
 *
 * 继承 agent-console app-shell，侧栏选中「工单管理」（路由 /tickets，壳层定义）。
 * 内容区（PRD）：顶部筛选栏（类型/状态/技能组 Select + 搜索 + 重置）+ 工单列表
 * （ID + 主文案 + 关联客户 + 创建时间 + 状态徽章 + 行内操作按钮组按状态显示）。
 * 数据源：tickets store（api/tickets.ts mock 先行，坐席视角端点见 #44/#45）。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Close, Finished, Tickets } from '@element-plus/icons-vue'

import { useAuthStore } from '../stores/auth'
import { useTicketsStore } from '../stores/tickets'
import {
  SKILL_GROUP_LABELS,
  skillGroupLabel,
  ticketBadgeVariant,
  ticketStatusLabel,
  ticketTypeLabel,
  timeLabel,
} from '../api/tickets'
import type { AgentTicket } from '../api/tickets'

const store = useTicketsStore()
const auth = useAuthStore()
const router = useRouter()

onMounted(() => {
  if (auth.accessToken) void store.load(auth.accessToken)
})

/** 类型 Select 选项（办理类/工单类/全部）。 */
const typeOptions: { value: string; label: string }[] = [
  { value: 'all', label: '全部类型' },
  { value: 'transaction', label: '办理类' },
  { value: 'ticketing', label: '工单类' },
]

/** 状态 Select 选项（两状态机状态并集，PRD line 288-292）。 */
const statusOptions: { value: string; label: string }[] = [
  { value: 'all', label: '全部状态' },
  { value: 'pending', label: '待执行/待派单' },
  { value: 'dispatched', label: '已派单' },
  { value: 'processing', label: '执行中' },
  { value: 'in_progress', label: '处理中' },
  { value: 'awaiting_confirmation', label: '待确认' },
  { value: 'effective', label: '已生效' },
  { value: 'failed', label: '已失败' },
  { value: 'closed', label: '已关闭' },
  { value: 'cancelled', label: '已取消' },
]

/** 技能组 Select 选项（套餐业务组/故障报修组/投诉处理组）。 */
const skillOptions: { value: string; label: string }[] = [
  { value: 'all', label: '全部技能组' },
  ...Object.entries(SKILL_GROUP_LABELS).map(([value, label]) => ({ value, label })),
]

/** 选中行（row-selected 态）。 */
function selectRow(t: AgentTicket) {
  store.selectRow(t.id)
}

/** 行内操作按钮组（按状态显示，PRD §tickets(agent-console) 列表段）。 */
function rowActions(t: AgentTicket): 'dispatch' | 'execute' | 'close' | 'view' | null {
  if (t.ticket_type === 'ticketing' && t.status === 'pending') return 'dispatch' // 待派单
  if (t.ticket_type === 'transaction' && t.status === 'pending') return 'execute' // 待执行
  if (t.status === 'awaiting_confirmation') return 'close' // 待确认
  if (t.status === 'dispatched') return 'view' // 已派单
  return null // 已终结无操作
}

/** 服务密码复核 Modal（US-25）：待执行办理工单执行前，坐席引导用户再次输入服务密码。 */
const executingTicket = ref<AgentTicket | null>(null)
const reauthPassword = ref('')
const reauthing = ref(false)
const reauthError = ref('')

function openReauth(t: AgentTicket) {
  executingTicket.value = t
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
  reauthing.value = true
  reauthError.value = ''
  try {
    await store.execute(executingTicket.value.id, password, auth.accessToken)
    executingTicket.value = null
  } catch (err) {
    reauthError.value = err instanceof Error ? err.message : '执行失败，请重试'
  } finally {
    reauthing.value = false
  }
}

/** 创建工单 Modal（US-23）：工单类型 Select + 内容 textarea + 主按钮「创建」。 */
const showCreateModal = ref(false)
const newTicketType = ref<'transaction' | 'ticketing'>('ticketing')
const newTicketContent = ref('')
const creating = ref(false)
const createError = ref('')

function openCreateModal() {
  showCreateModal.value = true
  newTicketType.value = 'ticketing'
  newTicketContent.value = ''
  createError.value = ''
}

function closeCreateModal() {
  if (creating.value) return
  showCreateModal.value = false
}

async function submitCreateTicket() {
  const content = newTicketContent.value.trim()
  if (!content || creating.value) return
  creating.value = true
  createError.value = ''
  try {
    await store.create({ ticket_type: newTicketType.value, content }, auth.accessToken)
    showCreateModal.value = false
  } catch (err) {
    createError.value = err instanceof Error ? err.message : '创建工单失败，请重试'
  } finally {
    creating.value = false
  }
}

/** 工单类型图标（办理类 Finished / 工单类 Tickets，PRD §tickets 列表段）。 */
function typeIcon(t: AgentTicket): unknown {
  return t.ticket_type === 'transaction' ? Finished : Tickets
}

/** 查看工单详情（US-24/27/29：已派单「查看」跳详情）。 */
function viewDetail(t: AgentTicket) {
  router.push({ name: 'ticket-detail', params: { id: String(t.id) } })
}
</script>

<template>
  <div data-testid="tickets-view" class="tickets-view">
    <h1 data-testid="tickets-title" class="tickets-title">工单管理</h1>

    <!-- 顶部筛选栏：白底 shadow-xs 圆角 8px 卡片（PRD §tickets(agent-console) 筛选栏段） -->
    <div data-testid="ticket-filters" class="ticket-filters">
      <label class="ticket-filters__field">
        <span class="ticket-filters__label">工单类型</span>
        <select
          v-model="store.filters.type"
          data-testid="filter-type"
          class="ticket-filters__select"
        >
          <option v-for="opt in typeOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
      </label>
      <label class="ticket-filters__field">
        <span class="ticket-filters__label">状态</span>
        <select
          v-model="store.filters.status"
          data-testid="filter-status"
          class="ticket-filters__select"
        >
          <option v-for="opt in statusOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
      </label>
      <label class="ticket-filters__field">
        <span class="ticket-filters__label">技能组</span>
        <select
          v-model="store.filters.skillGroup"
          data-testid="filter-skill"
          class="ticket-filters__select"
        >
          <option v-for="opt in skillOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
      </label>
      <label class="ticket-filters__field ticket-filters__field--search">
        <span class="ticket-filters__label">搜索</span>
        <input
          v-model="store.filters.keyword"
          data-testid="filter-search"
          class="ticket-filters__search"
          type="text"
          placeholder="搜索工单/客户"
        />
      </label>
      <button
        data-testid="filter-reset"
        class="btn btn--text"
        type="button"
        @click="store.resetFilters"
      >
        重置
      </button>
      <button
        data-testid="create-ticket-btn"
        class="btn btn--outline btn--sm"
        type="button"
        @click="openCreateModal"
      >
        创建工单
      </button>
    </div>

    <!-- 加载变体（PRD §tickets(agent-console) 变体段「加载变体」/ DESIGN.md §5.10 骨架屏）：列表骨架屏 -->
    <div v-if="store.loading" data-testid="tickets-skeleton" class="skeleton-list" aria-busy="true">
      <div v-for="n in 3" :key="n" data-testid="skeleton-item" class="skeleton-item">
        <div class="skeleton-item__icon" />
        <div class="skeleton-item__lines">
          <div class="skeleton-item__line skeleton-item__line--long" />
          <div class="skeleton-item__line skeleton-item__line--short" />
        </div>
      </div>
    </div>

    <!-- 工单列表（可滚动；每行 56px 宽松，PRD §tickets(agent-console) 列表段） -->
    <div
      v-else-if="!store.loading && store.filteredTickets.length > 0"
      data-testid="tickets-list"
      class="tickets-list"
    >
      <div
        v-for="t in store.filteredTickets"
        :key="t.id"
        data-testid="ticket-row"
        :data-id="String(t.id)"
        :data-selected="store.selectedId === t.id ? 'true' : 'false'"
        :class="{ 'ticket-row--selected': store.selectedId === t.id }"
        class="ticket-row"
        role="button"
        tabindex="0"
        @click="selectRow(t)"
      >
        <span data-testid="ticket-id" class="ticket-row__id">#{{ t.id }}</span>
        <el-icon :size="16" class="ticket-row__icon" aria-hidden="true">
          <component :is="typeIcon(t)" />
        </el-icon>
        <div class="ticket-row__body">
          <p data-testid="ticket-title" class="ticket-row__title">
            {{ ticketTypeLabel(t.ticket_type) }} · {{ t.content }}
          </p>
          <p class="ticket-row__meta">
            <span data-testid="ticket-customer">{{ t.customer_phone ?? '访客' }}</span>
            <span data-testid="ticket-skill"> · {{ skillGroupLabel(t.skill_group) }}</span>
            <span data-testid="ticket-time"> · {{ timeLabel(t.created_at) }}</span>
          </p>
        </div>
        <span
          data-testid="ticket-status-badge"
          class="badge"
          :data-variant="ticketBadgeVariant(t)"
          :class="`badge--${ticketBadgeVariant(t)}`"
          >{{ ticketStatusLabel(t) }}</span
        >
        <div v-if="rowActions(t)" data-testid="row-action" class="ticket-row__actions">
          <button
            v-if="rowActions(t) === 'dispatch'"
            data-testid="row-action-dispatch"
            class="btn btn--primary btn--sm"
            type="button"
            @click.stop="store.dispatch(t.id, auth.accessToken)"
          >
            派单
          </button>
          <button
            v-else-if="rowActions(t) === 'execute'"
            data-testid="row-action-execute"
            class="btn btn--primary btn--sm"
            type="button"
            @click.stop="openReauth(t)"
          >
            执行
          </button>
          <button
            v-else-if="rowActions(t) === 'close'"
            data-testid="row-action-close"
            class="btn btn--outline btn--sm"
            type="button"
            @click.stop="store.close(t.id, auth.accessToken)"
          >
            关闭
          </button>
          <button
            v-else-if="rowActions(t) === 'view'"
            data-testid="row-action-view"
            class="btn btn--text btn--sm"
            type="button"
            @click.stop="viewDetail(t)"
          >
            查看
          </button>
        </div>
      </div>
    </div>

    <!-- 筛选无结果变体（PRD 变体段「筛选无结果变体」：空状态主文案 + 描边按钮「清除筛选」） -->
    <div
      v-else-if="!store.loading && store.hasActiveFilters"
      data-testid="tickets-no-result"
      class="empty-state"
    >
      <el-icon :size="64" class="empty-state__illustration" aria-hidden="true">
        <Tickets />
      </el-icon>
      <p class="empty-state__title">无匹配工单</p>
      <button
        data-testid="clear-filters"
        class="btn btn--outline"
        type="button"
        @click="store.resetFilters"
      >
        清除筛选
      </button>
    </div>

    <!-- 空状态（PRD 变体段「空状态」：居中 empty-state 插画 + 主辅文案） -->
    <div v-else data-testid="tickets-empty" class="empty-state">
      <el-icon
        data-testid="tickets-empty-illustration"
        :size="64"
        class="empty-state__illustration"
        aria-hidden="true"
      >
        <Tickets />
      </el-icon>
      <p class="empty-state__title">暂无工单</p>
      <p class="empty-state__hint">调整筛选条件或创建新工单</p>
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

    <!-- 创建工单 Modal（US-23，同 active-chat 规格：工单类型 Select + 内容 textarea + 主按钮「创建」） -->
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
  </div>
</template>

<style scoped>
/* surface-base 底 + 24px 内边距（PRD §tickets(agent-console) 内容区；DESIGN.md §2 surface-base）。 */
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

/* 筛选栏：白底 shadow-xs 圆角 8px 卡片，内边距 12×16（PRD §tickets 筛选栏段；DESIGN.md §5.3）。 */
.ticket-filters {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #ffffff;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04); /* shadow-xs */
}

.ticket-filters__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ticket-filters__field--search {
  flex: 1;
  min-width: 160px;
}

.ticket-filters__label {
  font-size: 12px;
  font-weight: 500;
  color: #6b7280; /* Neutral 500 */
}

/* Select/输入：同 §5.2 输入规格（默认 1px Neutral 300 描边，聚焦 shadow-focus）。 */
.ticket-filters__select,
.ticket-filters__search {
  height: 36px;
  padding: 0 12px;
  border: 1px solid #d1d5db; /* Neutral 300 */
  border-radius: 6px;
  background: #ffffff;
  font-size: 14px;
  color: #1f2937;
  box-sizing: border-box;
  font-family: inherit;
}

.ticket-filters__search {
  width: 200px;
}

.ticket-filters__select:focus,
.ticket-filters__search:focus {
  outline: none;
  border-color: transparent;
  box-shadow: 0 0 0 2px #c9deff; /* shadow-focus（Primary 100） */
}

/* 工单列表：每行 56px 宽松、白底、底部分隔线 Neutral 100（DESIGN.md §5.4 列表行）。 */
.tickets-list {
  background: #ffffff;
}

.ticket-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 56px;
  padding: 12px 16px;
  border-bottom: 1px solid #f3f4f6; /* Neutral 100 */
  cursor: pointer;
}

.ticket-row:hover {
  background: #f4f8ff; /* primary-tint-bg */
}

/* 选中行：primary-tint-bg-strong 背景 + 左侧 3px Primary 500 色条（DESIGN.md §5.4 选中态）。 */
.ticket-row--selected {
  background: #e0ebff; /* primary-tint-bg-strong */
  color: #0d5be6; /* Primary 600 */
  border-left: 3px solid #1a6fff; /* Primary 500 */
  padding-left: 13px;
}

.ticket-row__id {
  font-size: 12px;
  font-weight: 500;
  line-height: 18px;
  color: #6b7280; /* Neutral 500 */
  flex-shrink: 0;
}

.ticket-row__icon {
  color: #4b5563; /* Neutral 600 */
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

.ticket-row--selected .ticket-row__title {
  color: #0d5be6; /* Primary 600 */
}

/* 辅助文案：Body-sm 13px(400) Neutral 500（PRD §tickets 列表段）。 */
.ticket-row__meta {
  margin: 2px 0 0;
  font-size: 13px;
  line-height: 20px;
  color: #6b7280;
}

/* 行内操作按钮组：小号 28px 按钮（DESIGN.md §5.1 尺寸）。 */
.ticket-row__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
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

.badge--warning {
  background: #fff6e0; /* semantic-warning-tint-bg */
  color: #f57f17; /* semantic-warning 700 */
}

.badge--info {
  background: #e8f4fb; /* semantic-info-tint-bg */
  color: #01579b; /* semantic-info 700 */
}

.badge--success {
  background: #ebf5ec; /* semantic-success-tint-bg */
  color: #1b5e20; /* semantic-success 700 */
}

.badge--error {
  background: #fceaea; /* semantic-error-tint-bg */
  color: #b71c1c; /* semantic-error 700 */
}

.badge--neutral {
  background: #f3f4f6; /* Neutral 100 */
  color: #374151; /* Neutral 700 */
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

.empty-state__illustration {
  color: #d1d5db; /* Neutral 300 */
  margin-bottom: 16px;
}

.empty-state__title {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  line-height: 22px;
  color: #374151; /* Neutral 700 */
}

.empty-state__hint {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 20px;
  color: #6b7280; /* Neutral 500 */
}

/* ---- 按钮（DESIGN.md §5.1）：主 36px / 小号 28px / 描边 / 文字 ---- */
.btn {
  flex-shrink: 0;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  font-family: inherit;
}

.btn--sm {
  height: 28px;
  padding: 0 12px;
  font-size: 13px;
}

.btn--primary {
  background: #1a6fff; /* Primary 500 */
  color: #ffffff;
}

.btn--primary:hover {
  background: #0d5be6; /* Primary 600 */
}

.btn--outline {
  background: transparent;
  color: #1a6fff; /* Primary 500 */
  border: 1px solid transparent;
}

.btn--outline:hover {
  background: #f4f8ff; /* primary-tint-bg */
  border-color: #1a6fff;
}

.btn--text {
  height: 32px;
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
  color: #1f2937;
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
</style>
