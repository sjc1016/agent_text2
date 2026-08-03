/**
 * customer-web customers REST 客户端（B13 契约，#53）。
 *
 * 后端契约（backend/app/customers/routes.py）：
 *   GET /api/customers/me（Bearer）→ 200 CustomerMeOut（当前客户账户资料）
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（同 conversations.ts）。
 */

/** 当前客户账户资料（镜像 backend CustomerMeOut；plan_name 供账号卡片套餐简述）。 */
export interface CustomerMe {
  id: number
  phone: string
  name: string | null
  balance: number
  plan_name: string | null
  contract_expiry_date: string | null
}

/** Bearer 请求头（REST 用 Authorization header——PRD 实现决策 › 认证与会话）。 */
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

/** 拉取当前客户账户资料（US-17 账号信息；未认证 401 由后端守卫）。 */
export async function getCustomerMe(token: string): Promise<CustomerMe> {
  const response = await expectOk(await fetch('/api/customers/me', { headers: authHeaders(token) }))
  return (await response.json()) as CustomerMe
}
