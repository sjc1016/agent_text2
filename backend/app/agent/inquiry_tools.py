"""B5 查询类 tools（注册进 ToolRegistry，供 Assistant 对话流调用）。

PRD 依据：
  - 实现决策 › API 契约（/inquiries/* 查询类业务能力）
  - 测试决策 › tool 调用 seam（查询类业务能力返回正确数据，纯函数与 LLM 解耦）
  - CONTEXT.md › 业务能力 / 查询类（只读，Customer 认证后可直接调用）
  - 用户故事 US-3~US-7

DB 依赖：ToolContext.db 由调用方（WS 路由 / 测试）注入，tool 保持可测纯函数。
认证边界：查询类要求 Customer 认证（ToolContext.customer_id）；未认证 → 诚实拒绝
（CONTEXT › 查询类：Customer 认证后可直接调用，Visitor 仅通用咨询）。
敏感审计：话费/合约/号码属敏感数据（CONTEXT › 审计日志），tool 经 ctx.audit_hook
记录 inquiry.* 事件（hook 由调用方注入）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agent.tools import ToolContext, ToolRegistry, tool
from app.inquiry.service import get_customer_account, list_value_added_services


def _require_db(ctx: ToolContext) -> Session:
    if ctx.db is None:
        raise RuntimeError("查询类 tool 需要 ToolContext.db（数据库会话）")
    return ctx.db


def _audit(ctx: ToolContext, action: str, account_id: int | None = None) -> None:
    """经 audit_hook 记录查询事件（敏感数据访问留痕，CONTEXT › 审计日志）。"""
    if ctx.audit_hook is not None:
        ctx.audit_hook(
            {
                "type": action,
                "customer_id": ctx.customer_id,
                "account_id": account_id,
            }
        )


@tool(name="balance_lookup", description="查询当前话费余额（元）")
def balance_lookup(ctx: ToolContext) -> str:
    """话费余额查询（验收标准1 / US-3）：返回账户当前余额。"""
    db = _require_db(ctx)
    if ctx.customer_id is None:
        return "查询话费余额需要先认证（请通过手机号 + 服务密码登录）。"
    account = get_customer_account(db, ctx.customer_id)
    if account is None:
        return "未查询到您的账户信息，请稍后重试。"
    _audit(ctx, "inquiry.balance", account.id)
    return f"您当前的话费余额为 {account.balance:g} 元。"


@tool(name="plan_detail_lookup", description="查询当前套餐详情（套餐名与月费）")
def plan_detail_lookup(ctx: ToolContext) -> str:
    """当前套餐详情查询（验收标准2 / US-4）。"""
    db = _require_db(ctx)
    if ctx.customer_id is None:
        return "查询当前套餐需要先认证（请通过手机号 + 服务密码登录）。"
    account = get_customer_account(db, ctx.customer_id)
    if account is None:
        return "未查询到您的账户信息，请稍后重试。"
    _audit(ctx, "inquiry.plan", account.id)
    return f"您当前套餐为 {account.plan_name}，月费 {account.plan_price:g} 元。"


@tool(name="usage_lookup", description="查询本月通话与流量使用量")
def usage_lookup(ctx: ToolContext) -> str:
    """通话/流量使用量查询（验收标准2 / US-5）。"""
    db = _require_db(ctx)
    if ctx.customer_id is None:
        return "查询使用量需要先认证（请通过手机号 + 服务密码登录）。"
    account = get_customer_account(db, ctx.customer_id)
    if account is None:
        return "未查询到您的账户信息，请稍后重试。"
    _audit(ctx, "inquiry.usage", account.id)
    return f"本月通话使用 {account.call_used}，流量使用 {account.data_used}。"


@tool(name="contract_lookup", description="查询合约到期时间")
def contract_lookup(ctx: ToolContext) -> str:
    """合约到期时间查询（验收标准2 / US-6）。"""
    db = _require_db(ctx)
    if ctx.customer_id is None:
        return "查询合约信息需要先认证（请通过手机号 + 服务密码登录）。"
    account = get_customer_account(db, ctx.customer_id)
    if account is None:
        return "未查询到您的账户信息，请稍后重试。"
    _audit(ctx, "inquiry.contract", account.id)
    return f"您的合约将于 {account.contract_expiry_date} 到期。"


@tool(name="value_added_lookup", description="查询已订购增值业务列表")
def value_added_lookup(ctx: ToolContext) -> str:
    """已订购增值业务查询（验收标准2 / US-7）。"""
    db = _require_db(ctx)
    if ctx.customer_id is None:
        return "查询增值业务需要先认证（请通过手机号 + 服务密码登录）。"
    services = list_value_added_services(db, ctx.customer_id)
    if not services:
        return "您暂未订购增值业务。"
    _audit(ctx, "inquiry.vadd")
    names = "、".join(
        f"{s.service_name}（{s.monthly_fee:g} 元/月）"
        if s.monthly_fee is not None
        else s.service_name
        for s in services
    )
    return f"您已订购以下增值业务：{names}。"


#: 本模块全部工具（供 ToolRegistry 批量注册）
INQUIRY_TOOLS = [
    balance_lookup,
    plan_detail_lookup,
    usage_lookup,
    contract_lookup,
    value_added_lookup,
]


def register_inquiry_tools(registry: ToolRegistry) -> None:
    """将查询类 tools 注册进 ToolRegistry（B5/B6/#24 组合时统一调用）。"""
    for fn in INQUIRY_TOOLS:
        registry.register(fn)
