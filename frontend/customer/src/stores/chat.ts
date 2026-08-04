import { defineStore } from 'pinia'

import { reauth } from '../api/auth'
import { confirmTransaction, executeTicket } from '../api/transactions'
import { refreshSessionAccessToken } from '../api/http'
import { ChatWsClient } from '../api/ws'
import { createConversation, type ChatMessage } from '../api/conversations'
import { useSessionStore } from './session'
import { useUiStore } from './ui'
import type {
  ConversationStatePayload,
  LlmTokenPayload,
  MessageNewPayload,
  ReauthRequiredPayload,
  SecondConfirmPayload,
  SystemMessagePayload,
  WsEvent,
} from 'shared/events'

/**
 * chat store（#24 UI-C-3）：承载主会话对话流 + 三类内嵌组件的数据源。
 *
 * 职责边界（深模块）：
 *   - conversationId / messages：对话流数据；新会话经 REST POST /conversations 创建。
 *   - assistantPending / assistantPartial：助理流式生成态（信号脉冲 → 逐 token 文本）。
 *   - pendingConfirm / pendingReauth：二次确认 / 服务密码复核 Modal 数据（WS 事件驱动）。
 *   - failedContent：发送失败待重发内容（WS 未连接时发送返回 false，错误态重发按钮）。
 *   - WS 生命周期：connectWs / disconnect；断线语义写入 ui store（顶栏断线条）。
 *
 * WS 事件消费（envelope {event, data}，契约 shared/events.ts SSOT）：
 *   llm.token / message.new / system.message / conversation.state /
 *   second.confirm / reauth.required；其余事件（handoff.*、ticket.* 等）本页不消费。
 */

/**
 * WS accept 后服务端推送的会话建立提示（backend/app/ws/routes.py _SESSION_OPENED_CONTENT）。
 * 新会话空状态的问候气泡由前端渲染（PRD chat 空状态变体「助理先发问候」），
 * 该瞬时系统提示与问候语义重复，store 吞掉不放入对话流。
 */
const SESSION_OPENED_HINT = '会话已建立，请问有什么可以帮您？'

/** 系统消息无持久化 id：用负序号合成（仅作 v-for key）。 */
let systemIdSeq = 0

let wsClient: ChatWsClient | null = null

export const useChatStore = defineStore('chat', {
  state: () => ({
    conversationId: null as number | null,
    messages: [] as ChatMessage[],
    /** 助理生成中（信号脉冲）；首 token 置 true，assistant 消息落库后置 false。 */
    assistantPending: false,
    /** llm.token 累积片段（信号脉冲切换为可渲染文本后逐 token 追加）。 */
    assistantPartial: '',
    /** 二次确认 Modal 数据（second.confirm 事件）。 */
    pendingConfirm: null as SecondConfirmPayload | null,
    /** 服务密码复核 Modal 数据（reauth.required 事件）。 */
    pendingReauth: null as ReauthRequiredPayload | null,
    /** 发送失败待重发内容（WS 未连接 → 错误态重发按钮）。 */
    failedContent: null as string | null,
  }),
  getters: {
    /** Handed-off（转接中）：输入区禁用 + 转接提示（States 矩阵 disabled）。 */
    isHandedOff(): boolean {
      return useSessionStore().conversationState === 'handed_off'
    },
    /** 空状态：新会话无任何消息且无失败内容 → 渲染助理问候气泡。 */
    showGreeting(): boolean {
      return this.messages.length === 0 && this.failedContent === null
    },
  },
  actions: {
    /** 确保存在活跃会话：未创建则 POST /conversations（已认证客户，#24 对话页入口）。 */
    async ensureConversation(): Promise<void> {
      const session = useSessionStore()
      if (this.conversationId !== null) return
      if (!session.isAuthenticated) return
      // createConversation 内部走 401 自动刷新（#65）：access 过期 → 刷新后重试建会话。
      const conversation = await createConversation(session.accessToken)
      this.conversationId = conversation.id
    },

    /** 建立 WS 连接（accessToken 查询参数鉴权；断线语义写入 ui store）。 */
    connectWs(): void {
      const session = useSessionStore()
      if (!session.accessToken) return
      const ui = useUiStore()
      wsClient?.close()
      wsClient = new ChatWsClient({
        getToken: () => useSessionStore().accessToken,
        onEvent: (event) => this.handleWsEvent(event),
        onBrokenChange: (broken) => ui.setWsBroken(broken),
        // WS 4401（access token 失效）→ 单飞刷新；刷新后 store 写回新 token，
        // 重连时 getToken 取到新 token；刷新失败 → http 层 logout（视图 watcher 收尾）。
        onAuthRejected: () => {
          refreshSessionAccessToken().catch(() => {
            // 刷新失败已 logout，无需在此处理（避免未捕获 rejection）
          })
        },
      })
      wsClient.connect()
    },

    /** 对话页入口：先确保会话，再连 WS（消息/状态事件落在已创建会话上）。 */
    async init(): Promise<void> {
      await this.ensureConversation()
      this.connectWs()
    },

    /** 页面卸载时关闭连接（不再自动重连）。 */
    disconnect(): void {
      wsClient?.close()
      wsClient = null
    },

    /**
     * 退出登录（US-17 / issue #65）：关闭 WS（停止重连）+ 清空对话流数据。
     * 视图层在登出（含 refresh 失败自动登出）时调用。
     */
    logout(): void {
      wsClient?.close()
      wsClient = null
      this.reset()
      useUiStore().setWsBroken(false)
    },

    /**
     * 发送用户消息；WS 未连接时记录 failedContent 供重发（States 矩阵 error）。
     * issue #65：会话未创建（conversationId null，如建会话 401 被吞）不再静默——
     * 记录 failedContent 显示明确错误态（用户气泡 + 重发按钮）。
     */
    sendMessage(content: string): void {
      if (this.isHandedOff) return
      if (!this.conversationId) {
        this.failedContent = content
        return
      }
      const sent = (wsClient?.sendMessage(this.conversationId, content) ?? false) === true
      if (sent) {
        this.failedContent = null
      } else {
        this.failedContent = content
      }
    },

    /** 重发失败消息（错误态「重发」按钮）；会话未创建时先建会话再发（#65）。 */
    async retrySend(): Promise<void> {
      if (this.failedContent === null) return
      if (this.conversationId === null) await this.ensureConversation()
      if (this.conversationId === null || this.failedContent === null) return
      const sent =
        (wsClient?.sendMessage(this.conversationId, this.failedContent) ?? false) === true
      if (sent) this.failedContent = null
    },

    /**
     * 二次确认（States 矩阵 second-confirm-modal）：确认办理 → 创建 Ticket 入队（US-8~US-11）。
     * 办理内容取 business_impact.summary（结构化业务影响的一句话摘要，写入 Ticket.content）。
     * 成功关闭 Modal；失败抛错（视图捕获展示 inline 错误文案）。
     */
    async confirmPending(): Promise<void> {
      const session = useSessionStore()
      const confirm = this.pendingConfirm
      if (!confirm || !session.isAuthenticated) return
      await confirmTransaction(
        session.accessToken,
        confirm.conversation_id,
        confirm.business_impact.summary,
      )
      this.pendingConfirm = null
    },

    /** 取消二次确认：仅关闭 Modal，不创建 Ticket（CONTEXT › 办理入队：未确认不入队）。 */
    cancelConfirm(): void {
      this.pendingConfirm = null
    },

    /**
     * 复核并执行（States 矩阵 reauth-modal）：/auth/reauth 复核服务密码取 execute_token
     * → /transactions/{id}/execute 执行（US-12，补偿控制）。
     * 成功关闭 Modal；失败抛错（视图捕获展示 inline 错误文案，Modal 保持打开）。
     */
    async reauthAndExecute(servicePassword: string): Promise<void> {
      const session = useSessionStore()
      const req = this.pendingReauth
      if (!req || !session.isAuthenticated) return
      const { execute_token } = await reauth(session.accessToken, servicePassword)
      await executeTicket(execute_token, req.ticket_id)
      this.pendingReauth = null
    },

    /** 取消执行复核：仅关闭 Modal，Ticket 保持待执行（可稍后再触发复核）。 */
    cancelReauth(): void {
      this.pendingReauth = null
    },

    /** 退出登录时清空对话流状态（#11：避免旧会话数据残留，US-17「清除会话」）。 */
    reset(): void {
      this.conversationId = null
      this.messages = []
      this.assistantPending = false
      this.assistantPartial = ''
      this.pendingConfirm = null
      this.pendingReauth = null
      this.failedContent = null
    },

    /** 消费 WS 事件（ChatWsClient onEvent 回调；仅本页相关事件）。 */
    handleWsEvent(event: WsEvent): void {
      switch (event.event) {
        case 'llm.token': {
          // WsEvent 为泛型联合（data 未自动收窄），按事件名断言具体 payload。
          const data = event.data as LlmTokenPayload
          this.assistantPending = true
          this.assistantPartial += data.token
          break
        }
        case 'message.new': {
          const message = event.data as MessageNewPayload
          if (this.conversationId !== null && message.conversation_id !== this.conversationId) break
          this.messages.push(message as ChatMessage)
          if (message.source === 'assistant') {
            this.assistantPending = false
            this.assistantPartial = ''
          }
          if (message.source === 'user') this.failedContent = null
          break
        }
        case 'system.message': {
          const system = event.data as SystemMessagePayload
          if (system.content === SESSION_OPENED_HINT) break
          this.assistantPending = false
          this.messages.push({
            id: --systemIdSeq,
            conversation_id: this.conversationId ?? 0,
            source: 'system',
            content: system.content,
            created_at: system.created_at,
          })
          break
        }
        case 'conversation.state': {
          const state = event.data as ConversationStatePayload
          this.assistantPending = false
          useSessionStore().setConversationState(state.new_state)
          break
        }
        case 'second.confirm':
          this.pendingConfirm = event.data as SecondConfirmPayload
          break
        case 'reauth.required':
          this.pendingReauth = event.data as ReauthRequiredPayload
          break
        default:
          break
      }
    },
  },
})
