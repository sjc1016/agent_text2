<script setup lang="ts">
/**
 * agent-console「工单详情」页（PRD 页面清单 §ticket-detail；issue #23 UI-A-6）。
 *
 * 继承 agent-console app-shell，侧栏选中「工单管理」（路由 /tickets/:id，壳层定义）。
 * 内容区（PRD）：页头（返回图标按钮 + 标题「工单详情」+ 右侧状态徽章）+ 左右两栏——
 * 左栏（约 60%）：工单基本信息卡 + 状态流转时间线卡（当前态高亮 primary-tint-bg-strong）
 * + 操作区卡（按当前状态显示可用操作）；右栏（约 40%）审计日志卡（倒序 + 关键操作 Info 徽章）。
 * 数据源：api/tickets.ts getAgentTicketDetail（mock 先行，坐席视角端点见 #44/#45）。
 * 变体：loading（时间线与日志骨架屏）/ empty（审计日志「暂无审计记录」）/ terminated（操作区「工单已终结」）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Back, Close } from '@element-plus/icons-vue'

import { useAuthStore } from '../stores/auth'
import { useTicketsStore } from '../stores/tickets'
import {
  getAgentTicketDetail,
  SKILL_GROUP_LABELS,
  skillGroupLabel,
  ticketActionZone,
  ticketBadgeVariant,
  ticketStatusLabel,
  ticketTypeLabel,
  timeLabel,
  type AgentTicketDetail,
} from '../api/tickets'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const store = useTicketsStore()

const detail = ref<AgentTicketDetail | null>(null)
const loading = ref(false)

/** 页面顶部状态徽章（当前状态，US-24 流转结果即时可见）。 */
const statusBadge = computed(() => detail.value ?? undefined)

/** 操作区可用操作（States 矩阵 default：待派单/待执行/待确认/已终结/中间态）。 */
const actionZone = computed(() => (detail.value ? ticketActionZone(detail.value) : null))

/** 审计日志倒序（PRD §ticket-detail 审计日志段：按时间倒序，最新在前）。 */
const auditLogs = computed(() => {
  const logs = detail.value?.audit_logs ?? []
  return [...logs].sort((a, b) => b.created_at.localeCompare(a.created_at))
})

/** 派单技能组 Select 选中值（默认取工单当前技能组或首项；后端值为中文技能组）。 */
const dispatchGroup = ref('套餐业务组')

async function loadDetail() {
  loading.value = true
  try {
    detail.value = await getAgentTicketDetail(Number(route.params.id), auth.accessToken)
    dispatchGroup.value = detail.value.skill_group ?? '套餐业务组'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadDetail()
})

/** 返回工单列表（PRD §ticket-detail 顶栏返回图标按钮）。 */
function goBack() {
  router.push({ name: 'tickets' })
}

/* ---- 操作区（US-24 流转：派单到技能组 / 执行复核 / 确认关闭 / 取消工单） ---- */

async function submitDispatch() {
  if (detail.value === null || actionZone.value !== 'dispatch') return
  await store.dispatchToGroup(detail.value.id, dispatchGroup.value, auth.accessToken)
  await loadDetail()
}

async function submitClose() {
  if (detail.value === null || actionZone.value !== 'confirm') return
  await store.close(detail.value.id, auth.accessToken)
  await loadDetail()
}

async function submitCancel() {
  if (detail.value === null) return
  await store.cancel(detail.value.id, auth.accessToken)
  await loadDetail()
}

/* ---- 服务密码复核 Modal（US-25：待执行办理工单执行前，坐席引导用户再次输入服务密码） ---- */
const reauthOpen = ref(false)
const reauthPassword = ref('')
const reauthing = ref(false)
const reauthError = ref('')

function openReauth() {
  reauthOpen.value = true
  reauthPassword.value = ''
  reauthError.value = ''
}

function closeReauth() {
  if (reauthing.value) return
  reauthOpen.value = false
  reauthPassword.value = ''
}

async function submitReauth() {
  const password = reauthPassword.value.trim()
  if (!password || reauthing.value || detail.value === null || actionZone.value !== 'execute')
    return
  reauthing.value = true
  reauthError.value = ''
  try {
    await store.execute(detail.value.id, password, auth.accessToken)
    reauthOpen.value = false
    await loadDetail()
  } catch (err) {
    reauthError.value = err instanceof Error ? err.message : '执行失败，请重试'
  } finally {
    reauthing.value = false
  }
}
</script>

<template>
  <div data-testid="detail-view" class="detail-view">
    <!-- 页头：返回图标按钮 + 标题「工单详情」+ 右侧状态徽章（PRD §ticket-detail 顶栏段） -->
    <div class="detail-header">
      <button
        data-testid="detail-back"
        class="detail-header__back"
        type="button"
        aria-label="返回工单列表"
        @click="goBack"
      >
        <el-icon :size="16"><Back /></el-icon>
      </button>
      <h1 data-testid="detail-title" class="detail-header__title">工单详情</h1>
      <span
        v-if="statusBadge"
        data-testid="detail-status-badge"
        class="badge"
        :data-variant="ticketBadgeVariant(statusBadge)"
        :class="`badge--${ticketBadgeVariant(statusBadge)}`"
        >{{ ticketStatusLabel(statusBadge) }}</span
      >
    </div>

    <!-- 左右两栏（左主右辅，PRD §ticket-detail 内容区段） -->
    <div class="detail-layout">
      <!-- 左栏（flex 填充约 60%） -->
      <div class="detail-main">
        <!-- 工单基本信息卡：H2 工单类型标题 + Body 内容全文 + Caption 创建时间/创建者/关联客户 -->
        <section data-testid="info-card" class="card">
          <h2 data-testid="info-type" class="info-type">
            {{ detail ? ticketTypeLabel(detail.ticket_type) : '' }}
          </h2>
          <p v-if="!loading && detail" data-testid="info-content" class="info-content">
            {{ detail.content }}
          </p>
          <div v-if="loading" data-testid="info-skeleton" class="skeleton-lines" aria-busy="true">
            <div class="skeleton-line skeleton-line--long" />
            <div class="skeleton-line skeleton-line--short" />
          </div>
          <p v-if="!loading && detail" data-testid="info-meta" class="info-meta">
            创建于 {{ timeLabel(detail.created_at) }} · 创建者 {{ detail.creator }} · 关联客户
            {{ detail.customer_phone ?? '访客' }} · 技能组 {{ skillGroupLabel(detail.skill_group) }}
          </p>
        </section>

        <!-- 状态流转时间线卡：标题「状态流转」+ 纵向时间线（当前态高亮） -->
        <section data-testid="timeline-card" class="card">
          <h3 class="card__title">状态流转</h3>
          <!-- 加载变体：时间线骨架屏（States 矩阵 loading） -->
          <div
            v-if="loading"
            data-testid="timeline-skeleton"
            class="skeleton-lines"
            aria-busy="true"
          >
            <div v-for="n in 3" :key="n" class="skeleton-row">
              <div class="skeleton-line skeleton-line--sm" />
              <div class="skeleton-line skeleton-line--short" />
            </div>
          </div>
          <ol v-else-if="detail" data-testid="timeline" class="timeline">
            <li
              v-for="node in detail.timeline"
              :key="node.status"
              data-testid="timeline-node"
              :data-status="node.status"
              :data-current="node.is_current ? 'true' : 'false'"
              :class="{ 'timeline-node--current': node.is_current }"
              class="timeline-node"
            >
              <span class="timeline-node__badge">
                <span
                  class="badge"
                  :data-variant="ticketBadgeVariant(node)"
                  :class="`badge--${ticketBadgeVariant(node)}`"
                  >{{
                    ticketStatusLabel({ ticket_type: detail.ticket_type, status: node.status })
                  }}</span
                >
              </span>
              <span data-testid="timeline-node-time" class="timeline-node__time">{{
                timeLabel(node.at)
              }}</span>
              <span data-testid="timeline-node-operator" class="timeline-node__operator">{{
                node.operator
              }}</span>
            </li>
          </ol>
        </section>

        <!-- 操作区卡：按当前状态显示可用操作（US-24） -->
        <section data-testid="action-card" class="card">
          <h3 class="card__title">操作</h3>
          <!-- 待派单 → 主按钮「派单到技能组」+ Select 技能组 -->
          <div
            v-if="!loading && actionZone === 'dispatch'"
            data-testid="dispatch-zone"
            class="action-zone"
          >
            <select
              v-model="dispatchGroup"
              data-testid="skill-group-select"
              class="action-zone__select"
            >
              <option v-for="(label, value) in SKILL_GROUP_LABELS" :key="value" :value="value">
                {{ label }}
              </option>
            </select>
            <button
              data-testid="dispatch-btn"
              class="btn btn--primary"
              type="button"
              @click="submitDispatch"
            >
              派单到技能组
            </button>
          </div>
          <!-- 待执行 → 主按钮「执行」触发服务密码复核 Modal（US-25） -->
          <div
            v-else-if="!loading && actionZone === 'execute'"
            data-testid="execute-zone"
            class="action-zone"
          >
            <button
              data-testid="execute-btn"
              class="btn btn--primary"
              type="button"
              @click="openReauth"
            >
              执行
            </button>
          </div>
          <!-- 待确认 → 主按钮「确认关闭」+ 描边按钮「取消工单」 -->
          <div
            v-else-if="!loading && actionZone === 'confirm'"
            data-testid="confirm-zone"
            class="action-zone"
          >
            <button
              data-testid="close-btn"
              class="btn btn--primary"
              type="button"
              @click="submitClose"
            >
              确认关闭
            </button>
            <button
              data-testid="cancel-btn"
              class="btn btn--outline"
              type="button"
              @click="submitCancel"
            >
              取消工单
            </button>
          </div>
          <!-- 已终结变体：无按钮显示「工单已终结」居中（States 矩阵 terminated） -->
          <p
            v-else-if="!loading && actionZone === 'terminated'"
            data-testid="terminated-hint"
            class="action-hint"
          >
            工单已终结
          </p>
          <!-- 中间态（已派单/处理中/执行中等）：无可用操作 -->
          <p v-else-if="!loading && detail" data-testid="no-action-hint" class="action-hint">
            当前状态暂无可用操作
          </p>
        </section>
      </div>

      <!-- 右栏（约 40%）：审计日志卡（倒序 + 关键操作 Info 徽章） -->
      <aside data-testid="audit-card" class="card detail-side">
        <h3 class="card__title">审计日志</h3>
        <!-- 加载变体：日志骨架屏（States 矩阵 loading） -->
        <div v-if="loading" data-testid="audit-skeleton" class="skeleton-lines" aria-busy="true">
          <div v-for="n in 3" :key="n" class="skeleton-row">
            <div class="skeleton-line skeleton-line--sm" />
            <div class="skeleton-line skeleton-line--short" />
          </div>
        </div>
        <!-- 空状态：无记录居中 Caption「暂无审计记录」（States 矩阵 empty） -->
        <p
          v-else-if="!loading && auditLogs.length === 0"
          data-testid="audit-empty"
          class="audit-empty"
        >
          暂无审计记录
        </p>
        <ul v-else-if="!loading" data-testid="audit-list" class="audit-list">
          <li v-for="log in auditLogs" :key="log.id" data-testid="audit-row" class="audit-row">
            <span data-testid="audit-action" class="audit-row__action">{{ log.action }}</span>
            <span v-if="log.is_key" data-testid="audit-key-badge" class="badge badge--info"
              >Info</span
            >
            <p data-testid="audit-detail" class="audit-row__detail">{{ log.detail }}</p>
            <span data-testid="audit-time" class="audit-row__time">{{
              timeLabel(log.created_at)
            }}</span>
          </li>
        </ul>
      </aside>
    </div>

    <!-- 服务密码复核 Modal（US-25，同 tickets 页规格：坐席引导用户再次输入服务密码） -->
    <div v-if="reauthOpen" data-testid="reauth-modal" class="modal-overlay">
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
          <p data-testid="reauth-message" class="reauth-banner">
            执行「{{ detail?.content }}」需进行服务密码复核，请引导用户输入服务密码
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
/* surface-base 底 + 24px 内边距（PRD §ticket-detail 内容区；DESIGN.md §2 surface-base）。 */
.detail-view {
  padding: 24px;
  background: #f9fafb;
}

/* 页头：返回图标按钮 + H1 20px(600) Neutral 800 + 右侧状态徽章（DESIGN.md §5.5 / §3）。 */
.detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.detail-header__back {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #4b5563; /* Neutral 600 */
  cursor: pointer;
}

.detail-header__back:hover {
  background: #f3f4f6; /* Neutral 100 */
  color: #1f2937;
}

.detail-header__title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  line-height: 28px;
  color: #1f2937;
}

/* 左右两栏：左栏 flex 填充约 60%，右栏约 40%（PRD §ticket-detail 内容区段）。 */
.detail-layout {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.detail-main {
  flex: 1 1 60%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-side {
  flex: 1 1 40%;
  min-width: 0;
}

/* 卡片容器：白底 shadow-xs 圆角 8px 内边距 16px 无描边（DESIGN.md §5.3）。 */
.card {
  background: #ffffff;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04); /* shadow-xs */
  padding: 16px;
}

.card__title {
  margin: 0 0 12px;
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
  color: #1f2937;
}

/* ---- 基本信息卡 ---- */
.info-type {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  line-height: 26px;
  color: #1f2937;
}

.info-content {
  margin: 0 0 8px;
  font-size: 14px;
  line-height: 22px;
  color: #1f2937;
}

.info-meta {
  margin: 0;
  font-size: 12px;
  line-height: 18px;
  color: #6b7280; /* Neutral 500 */
}

/* ---- 状态流转时间线：纵向节点，每节点 36px 紧凑行（DESIGN.md §5.4） ---- */
.timeline {
  margin: 0;
  padding: 0;
  list-style: none;
}

.timeline-node {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 36px;
  padding: 4px 12px;
  border-radius: 6px;
}

.timeline-node__badge {
  flex-shrink: 0;
}

.timeline-node__time {
  flex-shrink: 0;
  font-size: 12px;
  line-height: 18px;
  color: #6b7280; /* Neutral 500 */
}

.timeline-node__operator {
  font-size: 13px;
  line-height: 20px;
  color: #374151; /* Neutral 700 */
}

/* 当前态高亮：primary-tint-bg-strong（States 矩阵 current-state-highlight）。 */
.timeline-node--current {
  background: #e0ebff; /* primary-tint-bg-strong */
  color: #0d5be6; /* Primary 600 */
}

.timeline-node--current .timeline-node__time {
  color: #0d5be6;
}

/* ---- 操作区 ---- */
.action-zone {
  display: flex;
  align-items: center;
  gap: 12px;
}

.action-zone__select {
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

.action-zone__select:focus {
  outline: none;
  border-color: transparent;
  box-shadow: 0 0 0 2px #c9deff; /* shadow-focus（Primary 100） */
}

/* 无操作提示：Body 14px Neutral 500 居中（已终结变体 / 中间态）。 */
.action-hint {
  margin: 0;
  text-align: center;
  font-size: 14px;
  line-height: 22px;
  color: #6b7280; /* Neutral 500 */
}

/* ---- 审计日志：列表行 36px 紧凑 + 关键操作 Info 徽章 ---- */
.audit-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.audit-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 8px;
  min-height: 36px;
  padding: 6px 0;
  border-bottom: 1px solid #f3f4f6; /* Neutral 100 */
}

.audit-row:last-child {
  border-bottom: none;
}

.audit-row__action {
  font-size: 12px;
  font-weight: 500;
  line-height: 18px;
  color: #6b7280; /* Neutral 500 */
}

.audit-row__detail {
  margin: 0;
  flex-basis: 100%;
  font-size: 13px;
  line-height: 20px;
  color: #1f2937; /* Neutral 800 */
}

.audit-row__time {
  margin-left: auto;
  font-size: 12px;
  line-height: 18px;
  color: #6b7280; /* Neutral 500 */
}

/* 空状态：审计日志无记录居中 Caption（States 矩阵 empty）。 */
.audit-empty {
  margin: 0;
  padding: 24px 0;
  text-align: center;
  font-size: 12px;
  line-height: 18px;
  color: #6b7280;
}

/* ---- 状态徽章（DESIGN.md §5.7 形态 + 五变体映射，同 tickets 页） ---- */
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

/* ---- 按钮（DESIGN.md §5.1）：主 36px / 大号 40px / 描边 / 文字 ---- */
.btn {
  flex-shrink: 0;
  height: 36px;
  padding: 0 16px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  font-family: inherit;
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

/* ---- 骨架屏（DESIGN.md §5.10：Neutral 100 底 + Neutral 200 高光扫描） ---- */
.skeleton-lines {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skeleton-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 36px;
}

.skeleton-line {
  height: 12px;
  border-radius: 4px;
  background: linear-gradient(90deg, #f3f4f6 25%, #e5e7eb 37%, #f3f4f6 63%);
  background-size: 400% 100%;
  animation: skeleton-scan 1.5s ease-in-out infinite;
}

.skeleton-line--long {
  width: 80%;
}

.skeleton-line--short {
  width: 40%;
}

.skeleton-line--sm {
  width: 64px;
}

@keyframes skeleton-scan {
  0% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0 50%;
  }
}
</style>
