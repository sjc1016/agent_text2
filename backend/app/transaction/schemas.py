"""B6 办理类业务 schema（Pydantic）。

PRD 依据：
  - 实现决策 › API 契约（/transactions/* 办理类业务能力发起）
  - 实现决策 › 办理流程（二次确认 + 入队 + 执行复核）
  - CONTEXT.md › 二次确认 / 办理入队 / 办理执行复核
  - 用户故事 US-8~US-12

四类办理（US-8~US-11）：套餐变更 / 增值订退 / 停机保号 / 充值缴费。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: 四类办理类型名（US-8~US-11）
TransactionTypeField = Literal["plan_change", "vadd_change", "suspend_hold", "recharge"]

#: 增值业务订退动作（subscribe 订购 / cancel 退订）
VaddActionField = Literal["subscribe", "cancel"]


class PlanChangeRequest(BaseModel):
    """发起套餐变更（US-8）。"""

    conversation_id: int = Field(..., description="所属会话")
    target_plan: str = Field(..., description="目标套餐名（套餐目录 Plan.name）")


class VaddChangeRequest(BaseModel):
    """发起增值业务订退（US-9）。"""

    conversation_id: int = Field(..., description="所属会话")
    service_name: str = Field(..., description="增值业务名")
    action: VaddActionField = Field(..., description="subscribe 订购 / cancel 退订")


class SuspendHoldRequest(BaseModel):
    """发起停机保号（US-10）。"""

    conversation_id: int = Field(..., description="所属会话")


class RechargeRequest(BaseModel):
    """发起充值缴费（US-11）。"""

    conversation_id: int = Field(..., description="所属会话")
    amount: float = Field(..., gt=0, description="充值金额（元，> 0）")


class TransactionConfirmRequest(BaseModel):
    """二次确认请求（POST /transactions/confirm）：用户显式确认 → 创建 Ticket 入队。"""

    conversation_id: int = Field(..., description="所属会话")
    content: str = Field(..., description="办理内容（写入 Ticket.content）")


class BusinessImpact(BaseModel):
    """结构化业务影响（二次确认 Modal 数据源，US-8~US-11）。

    四要素（CONTEXT › 二次确认）：套餐对比 / 生效时间 / 合约影响 / 费用变化。
    前端 second.confirm 事件据此渲染确认界面；LLM 亦可读取 summary 生成话术。
    """

    transaction_type: str = Field(..., description="办理类型")
    summary: str = Field(..., description="办理摘要（一句话）")
    plan_comparison: str = Field(..., description="套餐对比（当前 vs 目标）")
    effective_time: str = Field(..., description="生效时间")
    contract_impact: str = Field(..., description="合约影响")
    fee_change: str = Field(..., description="费用变化")


class TransactionInitiateOut(BaseModel):
    """发起办理响应：结构化业务影响（前端以此渲染二次确认 Modal）。"""

    model_config = ConfigDict(from_attributes=True)

    conversation_id: int
    transaction_type: str
    business_impact: BusinessImpact
