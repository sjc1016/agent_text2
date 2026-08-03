"""客户侧请求/响应 schema（Pydantic）。

PRD 依据：实现决策 › API 契约（RESTful 端点 /customers/me 当前客户资料）；
用户故事 US-14（查看工单状态与站内通知）、US-17（查看会话历史与账号信息）。
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class CustomerMeOut(BaseModel):
    """客户侧自身账户资料（GET /customers/me 响应，US-17 账号信息）。

    复用 B12（issue #44）同一账户数据源 get_customer_profile：
    CustomerAccount 话费余额/套餐名/合约到期；phone 为完整号码（客户读
    自身资料，与 /auth/me CustomerPublic 同语义，不脱敏）。
    未认证 → 401（CurrentCustomer 守卫）；无账户记录 → 404（不编造）。
    """

    id: int
    phone: str
    name: str | None
    balance: float
    plan_name: str | None
    contract_expiry_date: date | None


class NotificationOut(BaseModel):
    """客户侧站内通知项（GET /notifications 响应项，US-14 通知预览条数据源）。

    字段镜像 WS notification.push payload（NotificationPushPayload）与
    notifications 表；read 未读标记供前端预览条 filter；时间倒序由查询保证。
    """

    id: int
    ticket_id: int
    message: str
    read: bool
    created_at: datetime
