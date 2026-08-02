"""B6 办理类 tools（注册进 ToolRegistry，供 Assistant 对话流调用）。

PRD 依据：
  - 实现决策 › 办理流程（助理发起 → 二次确认）
  - 测试决策 › tool 调用 seam（办理类发起二次确认与入队逻辑）
  - CONTEXT.md › 办理规则 / 二次确认
  - 用户故事 US-8~US-11

tool 语义（与 #24 WS 路由约定的调用协议）：
  - 返回 JSON 字符串：{"status": "awaiting_confirmation", "transaction_type": ...,
    "business_impact": {...}}——调用方（WS 路由）解析后推送 second.confirm 事件，
    会话已由服务层流转进入 in_progress（等待二次确认）。
  - 失败/未认证返回自然语言错误（供 LLM 直接回复，诚实拒绝）。

DB 依赖：ToolContext.db 由调用方注入；tool 内 commit 会话状态流转（in_progress），
保持 tool 可独立执行（PRD 测试决策 › tool 调用 seam）。
审计：发起动作经 ctx.audit_hook 记录（CONTEXT › 审计日志：办理类发起）。
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.agent.tools import ToolContext, ToolRegistry, tool
from app.models import Conversation, Customer
from app.transaction.service import initiate_transaction


def _require_db(ctx: ToolContext) -> Session:
    if ctx.db is None:
        raise RuntimeError("办理类 tool 需要 ToolContext.db（数据库会话）")
    return ctx.db


def _audit(ctx: ToolContext, transaction_type: str) -> None:
    """经 audit_hook 记录办理发起事件（CONTEXT › 审计日志：办理类发起）。"""
    if ctx.audit_hook is not None:
        ctx.audit_hook(
            {
                "type": "transaction.initiate",
                "customer_id": ctx.customer_id,
                "conversation_id": ctx.conversation_id,
                "transaction_type": transaction_type,
            }
        )


def _initiate(ctx: ToolContext, transaction_type: str) -> str:
    """通用发起流程：认证守卫 → 会话守卫 → 服务层发起 → 返回二次确认标记 JSON。"""
    db = _require_db(ctx)
    if ctx.customer_id is None:
        return "办理类业务需要先认证（请通过手机号 + 服务密码登录）。"
    if ctx.conversation_id is None:
        return "未指定会话，无法发起办理。"

    customer = db.get(Customer, ctx.customer_id)
    conversation = db.get(Conversation, ctx.conversation_id)
    if customer is None:
        return "未找到您的认证信息，请重新登录。"
    if conversation is None:
        return "会话不存在，请刷新后重试。"

    try:
        impact = initiate_transaction(
            db, customer, conversation, transaction_type, dict(ctx.params)
        )
    except ValueError as exc:
        return f"{exc}。"
    db.commit()
    _audit(ctx, transaction_type)
    return json.dumps(
        {
            "status": "awaiting_confirmation",
            "transaction_type": transaction_type,
            "business_impact": impact.model_dump(),
        },
        ensure_ascii=False,
    )


@tool(name="plan_change", description="发起套餐变更（需二次确认）：参数 target_plan 目标套餐名")
def plan_change(ctx: ToolContext) -> str:
    """套餐变更发起（US-8）：返回二次确认标记，含套餐对比/生效时间/合约影响/费用变化。"""
    return _initiate(ctx, "plan_change")


@tool(
    name="vadd_change",
    description="发起增值业务订退（需二次确认）：参数 service_name 业务名、action subscribe/cancel",
)
def vadd_change(ctx: ToolContext) -> str:
    """增值业务订退发起（US-9）。"""
    return _initiate(ctx, "vadd_change")


@tool(name="suspend_hold", description="发起停机保号（需二次确认）：无参数")
def suspend_hold(ctx: ToolContext) -> str:
    """停机保号发起（US-10）。"""
    return _initiate(ctx, "suspend_hold")


@tool(name="recharge", description="发起充值缴费（需二次确认）：参数 amount 充值金额（元）")
def recharge(ctx: ToolContext) -> str:
    """充值缴费发起（US-11）。"""
    return _initiate(ctx, "recharge")


#: 本模块全部工具（供 ToolRegistry 批量注册）
TRANSACTION_TOOLS = [plan_change, vadd_change, suspend_hold, recharge]


def register_transaction_tools(registry: ToolRegistry) -> None:
    """将办理类 tools 注册进 ToolRegistry（B6/#24 组合时统一调用）。"""
    for fn in TRANSACTION_TOOLS:
        registry.register(fn)
