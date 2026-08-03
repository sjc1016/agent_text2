/**
 * agent-console API 客户端（REST）。
 *
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（前端一律 `/api/...` → nginx → 后端）。
 * B9 契约：POST /agents/login `{employee_id, password}` →
 *   200 `{access_token, refresh_token, token_type}` | 401 `{detail: "工号或密码错误"}`。
 * 队列契约（backend/app/agents/routes.py + schemas.py）：
 *   GET  /api/agents/queues（坐席 Bearer）→ 200 list[QueueItemOut]
 *
 * 数据缺口（backend issue #42）：
 *   - QueueItemOut 无转接原因（handoff_reason）字段；
 *   - 坐席无查询回呼请求工单的端点 —— 回呼分组由 queue store 本地 mock 驱动。
 */

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

/** 登录失败（后端 401，文案同 PRD login 错误变体）。 */
export class AgentLoginError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AgentLoginError'
  }
}

/**
 * 坐席登录（US-19）。
 * 失败抛 AgentLoginError；网络/非 401 错误同样收敛为默认文案，UI 统一走错误态。
 */
export async function agentLogin(employeeId: string, password: string): Promise<TokenResponse> {
  const response = await fetch('/api/agents/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ employee_id: employeeId, password }),
  })

  if (!response.ok) {
    let message = '工号或密码错误'
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') message = body.detail
    } catch {
      // 非 JSON 错误体：沿用默认文案
    }
    throw new AgentLoginError(message)
  }

  return (await response.json()) as TokenResponse
}

/** 待接入队列项（镜像后端 QueueItemOut）。 */
export interface QueueItem {
  conversation_id: number
  status: string
  created_at: string
  customer_id: number | null
  customer_phone: string | null
  last_user_message: string | null
}

/** Bearer 请求头（坐席 JWT，来自 auth store `agent.auth`）。 */
function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

async function expectOk(response: Response): Promise<Response> {
  if (!response.ok) {
    let detail = '请求失败'
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // 非 JSON 错误体：沿用默认文案
    }
    throw new Error(detail)
  }
  return response
}

/** 拉取待接入 Handoff 会话列表（US-20；按创建时间升序，号码已脱敏）。 */
export async function listQueueItems(token: string): Promise<QueueItem[]> {
  const response = await expectOk(
    await fetch('/api/agents/queues', { headers: authHeaders(token) }),
  )
  return (await response.json()) as QueueItem[]
}
