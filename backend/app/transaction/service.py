"""B6 办理类业务能力服务（深模块：四类办理 + 二次确认 + 入队 + 执行复核）。

PRD 依据：
  - 实现决策 › 办理流程（line 294-296）：助理发起 → 二次确认 → 创建 Ticket(Pending) 入队
    → 执行前服务密码复核 → Processing → 执行 → Effective/Failed
  - 实现决策 › API 契约（/transactions/* 办理类业务能力发起）
  - CONTEXT.md › 办理规则（二次确认 / 办理入队 / 办理执行复核）
  - 用户故事 US-8~US-12

设计说明（深模块）：
  - 对外接口小：initiate_transaction / confirm_transaction / trigger_execution_reauth /
    execute_transaction；内部封装四类办理的参数校验、结构化业务影响构建与状态机编排。
  - 一律复用 B7 create_ticket 入队（办理类不直接生效，CONTEXT › 办理入队）；
    会话状态流转复用 conversation.service（authenticated → in_progress → authenticated）。
  - 审计留痕由调用方（REST 路由 / tool audit_hook）负责，本服务不感知传输层与审计细节。
  - WS 推送（second.confirm / reauth.required / conversation.state / ticket.update）
    在 ws 模块（解耦：service 不感知传输层）。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.conversation.service import transition_conversation_state
from app.models import Conversation, Customer, Ticket
from app.ticket.service import create_ticket, transition_ticket_status
from app.transaction.schemas import BusinessImpact

#: 四类办理类型 → 中文标签（US-8~US-11）
TRANSACTION_LABELS: dict[str, str] = {
    "plan_change": "套餐变更",
    "vadd_change": "增值业务订退",
    "suspend_hold": "停机保号",
    "recharge": "充值缴费",
}

#: 合法办理类型集合（发起守卫）
TRANSACTION_TYPES: frozenset[str] = frozenset(TRANSACTION_LABELS)


def _enum_value(value: object) -> str:
    """提取枚举/字符串字段的字符串值（兼容 SQLAlchemy 枚举列直建为字符串的场景）。"""
    return value.value if hasattr(value, "value") else str(value)


def _normalize_params(transaction_type: str, params: dict) -> dict:
    """校验并规整办理参数；缺失/非法 → ValueError（路由层转 422）。

    各类必填：
      - plan_change: target_plan（目标套餐名）
      - vadd_change: service_name + action(subscribe/cancel)
      - suspend_hold: 无
      - recharge: amount（> 0）
    """
    if transaction_type == "plan_change":
        target = str(params.get("target_plan", "")).strip()
        if not target:
            raise ValueError("套餐变更需要目标套餐参数（target_plan）")
        return {"target_plan": target}
    if transaction_type == "vadd_change":
        service = str(params.get("service_name", "")).strip()
        action = str(params.get("action", "")).strip()
        if not service or action not in {"subscribe", "cancel"}:
            raise ValueError("增值业务订退需要 service_name 与 action（subscribe/cancel）")
        return {"service_name": service, "action": action}
    if transaction_type == "suspend_hold":
        return {}
    if transaction_type == "recharge":
        try:
            amount = float(params["amount"])
        except (TypeError, KeyError, ValueError):
            raise ValueError("充值缴费需要金额参数（amount）") from None
        if amount <= 0:
            raise ValueError("充值金额必须大于 0")
        return {"amount": amount}
    raise ValueError(f"未知办理类型: {transaction_type!r}")


def build_business_impact(
    db: Session, customer: Customer, transaction_type: str, params: dict
) -> BusinessImpact:
    """构建结构化业务影响（套餐对比/生效时间/合约影响/费用变化，CONTEXT › 二次确认）。

    参数已由 _normalize_params 规整；套餐变更会对比套餐目录（Plan）与当前账户，
    目标套餐不存在 → ValueError（诚实拒绝，不编造）。
    """
    if transaction_type == "plan_change":
        from app.general.service import query_plans
        from app.inquiry.service import get_customer_account

        target = params["target_plan"]
        plans = query_plans(db, names=[target])
        if not plans:
            raise ValueError(f"目标套餐不存在：{target}（请核对套餐名称）")
        target_plan = plans[0]
        account = get_customer_account(db, customer.id)
        current_plan = account.plan_name if account and account.plan_name else "无"
        current_price = account.plan_price if account and account.plan_price else 0.0
        plan_comparison = (
            f"当前 {current_plan}（{current_price:g} 元/月）"
            f" → 目标 {target_plan.name}（{target_plan.price:g} 元/月）"
        )
        fee_change = f"月费由 {current_price:g} 元/月变更为 {target_plan.price:g} 元/月"
        contract_impact = (
            "若处于合约期，变更可能影响合约优惠，以客服核实为准"
            if account and account.contract_expiry_date
            else "无在途合约约束"
        )
        return BusinessImpact(
            transaction_type="plan_change",
            summary=f"将套餐变更为{target_plan.name}",
            plan_comparison=plan_comparison,
            effective_time="申请通过后下个计费周期生效",
            contract_impact=contract_impact,
            fee_change=fee_change,
        )

    if transaction_type == "vadd_change":
        service = params["service_name"]
        action = params["action"]
        if action == "subscribe":
            return BusinessImpact(
                transaction_type="vadd_change",
                summary=f"订购增值业务{service}",
                plan_comparison=f"新增订购 {service}",
                effective_time="申请通过后立即生效",
                contract_impact="增值业务不产生合约约束",
                fee_change=f"月功能费以{service}资费为准（按自然月计费）",
            )
        return BusinessImpact(
            transaction_type="vadd_change",
            summary=f"退订增值业务{service}",
            plan_comparison=f"取消订购 {service}",
            effective_time="申请通过后立即生效",
            contract_impact="增值业务不产生合约约束",
            fee_change=f"退订后次月起不再收取{service}月功能费",
        )

    if transaction_type == "suspend_hold":
        return BusinessImpact(
            transaction_type="suspend_hold",
            summary="办理停机保号",
            plan_comparison="停机期间号码保留，不产生通话与流量使用",
            effective_time="申请通过后立即生效",
            contract_impact="停机保号期间合约期限顺延（以客服核实为准）",
            fee_change="停机保号月费 5 元/月（以套餐约定为准）",
        )

    amount = params["amount"]
    return BusinessImpact(
        transaction_type="recharge",
        summary=f"充值缴费 {amount:g} 元",
        plan_comparison="向当前号码充值，不影响套餐与合约",
        effective_time="支付成功后实时到账",
        contract_impact="无合约影响",
        fee_change=f"账户余额增加 {amount:g} 元",
    )


def initiate_transaction(
    db: Session,
    customer: Customer,
    conversation: Conversation,
    transaction_type: str,
    params: dict,
) -> BusinessImpact:
    """发起办理（US-8~US-11）：校验会话 authenticated → 构建影响 → 会话进入 In-Progress。

    CONTEXT › 二次确认：办理类业务执行前必须返回结构化确认提示；会话进入 In-Progress
    仅覆盖「等待二次确认」阶段（CONTEXT › 会话状态机）。

    Raises:
        ValueError: 未知类型 / 参数缺失非法 / 会话状态不可发起（路由层转 422）
    调用方负责 commit 与 WS 推送（second.confirm + conversation.state）。
    """
    if transaction_type not in TRANSACTION_TYPES:
        raise ValueError(f"未知办理类型: {transaction_type!r}")
    norm_params = _normalize_params(transaction_type, params)
    if conversation.status != "authenticated":
        raise ValueError(f"会话状态 {conversation.status!r} 不可发起办理（需 authenticated）")

    impact = build_business_impact(db, customer, transaction_type, norm_params)
    transition_conversation_state(db, conversation, "in_progress")
    db.flush()
    return impact


def confirm_transaction(
    db: Session,
    customer: Customer,
    conversation: Conversation,
    content: str,
) -> Ticket:
    """用户显式确认（US-8）：创建办理类 Ticket(Pending) 入队 → 会话回退 Authenticated。

    CONTEXT › 办理入队：未确认不入队；确认后一律经 Ticket，不直接生效。
    CONTEXT › 会话状态机：确认入队后会话回退 authenticated，可继续发起下一项办理。

    Raises:
        ValueError: 会话状态不可确认（非 In-Progress，路由层转 422）
    调用方负责 commit 与 WS 推送（conversation.state）。
    """
    if conversation.status != "in_progress":
        raise ValueError(f"会话状态 {conversation.status!r} 不可确认办理（需 in_progress）")

    ticket = create_ticket(
        db,
        conversation_id=conversation.id,
        ticket_type="transaction",
        content=content,
        creator_type="customer",
        creator_id=customer.id,
        customer_id=customer.id,
    )
    transition_conversation_state(db, conversation, "authenticated")
    db.flush()
    return ticket


def trigger_execution_reauth(db: Session, customer: Customer, ticket: Ticket) -> Ticket:
    """调度任务 seam（US-12）：办理类 Ticket 待执行 → 执行中的服务密码复核触发。

    CONTEXT › 办理执行复核：办理类 Ticket 从「待执行」进入「执行中」前，必须要求用户
    再次输入服务密码验证通过方可执行；作为单因素认证的补偿控制。

    本函数为「调度任务」入口（PRD 测试决策 › 调度任务 seam）：校验通过后由调用方
    （REST 路由 / 调度任务）推送 reauth.required，用户经 /auth/reauth 复核后
    凭 execute_token 调用 execute_transaction。

    Raises:
        ValueError: 工单归属/类型/状态不满足（路由层转 404/422）
    """
    if ticket.customer_id != customer.id:
        raise ValueError("无权操作该工单")
    if _enum_value(ticket.ticket_type) != "transaction":
        raise ValueError("仅办理类工单需要执行复核")
    if _enum_value(ticket.status) != "pending":
        raise ValueError(f"工单状态 {_enum_value(ticket.status)!r} 不可发起执行复核（需 pending）")
    db.flush()
    return ticket


def assert_executable_transaction(ticket: Ticket) -> None:
    """执行前置校验：办理类 + pending（execute_transaction 与坐席引导执行共享）。

    B12（issue #44 AC4）：坐席引导复核执行前先做可行性校验（422），
    再进入服务密码复核（401）——校验单点化，避免两条执行入口漂移。
    """
    if _enum_value(ticket.ticket_type) != "transaction":
        raise ValueError("仅办理类工单可执行")
    if _enum_value(ticket.status) != "pending":
        raise ValueError(f"工单状态 {_enum_value(ticket.status)!r} 不可执行（需 pending）")


def execute_transaction(db: Session, ticket: Ticket) -> Ticket:
    """执行办理（US-12）：复核通过后 pending → processing → 执行 → effective。

    PRD › 办理流程：… 服务密码复核 → Processing → 执行 → Effective/Failed。
    v1 执行生效为模拟后端业务系统（执行动作经审计留痕），业务效果由 Ticket 终态
    （effective/failed）与通知表达；真实后端业务系统接入时替换 _apply_effect。

    Raises:
        ValueError: 工单类型/状态不满足（路由层转 422）
    调用方负责 commit 与 WS 推送（ticket.update + notification.push）。
    """
    assert_executable_transaction(ticket)

    transition_ticket_status(db, ticket, "processing")
    _apply_effect(db, ticket)
    transition_ticket_status(db, ticket, "effective")
    db.flush()
    return ticket


def _apply_effect(db: Session, ticket: Ticket) -> None:
    """模拟后端业务系统执行办理（v1：动作留痕由审计负责，不真实变更业务数据）。

    接入真实后端系统时在此执行套餐变更/增值订退/停机保号/充值缴费；抛异常则
    execute_transaction 应改为流转 failed（v1 范围不做失败分支）。
    """
    # 执行动作审计（transaction.execute）由路由层统一记录
    return None
