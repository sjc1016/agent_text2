/**
 * customer-web customers REST 客户端（B13 契约，#53）。
 *
 * 后端契约（backend/app/customers/routes.py）：
 *   GET /api/customers/me（Bearer）→ 200 CustomerMeOut（当前客户账户资料）
 * 基址 `/api`：ADR 0006 / deploy/nginx.conf 反代契约（同 conversations.ts）。
 *
 * 鉴权统一走 api/http.ts（issue #65）：401 + WWW-Authenticate → 自动刷新 access token 重试。
 */

import { authedJson } from './http'

/** 当前客户账户资料（镜像 backend CustomerMeOut；plan_name 供账号卡片套餐简述）。 */
export interface CustomerMe {
  id: number
  phone: string
  name: string | null
  balance: number
  plan_name: string | null
  contract_expiry_date: string | null
}

/** 拉取当前客户账户资料（US-17 账号信息；未认证 401 由后端守卫）。 */
export async function getCustomerMe(token: string): Promise<CustomerMe> {
  return authedJson<CustomerMe>(token, '/api/customers/me')
}
