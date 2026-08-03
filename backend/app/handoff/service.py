"""Handoff 执行服务：服务时间规则 + 全忙判定 + 触发路由（正常转接 / 离线兜底）。

PRD 依据：
  - CONTEXT.md › 服务时间与离线兜底（坐席服务时间 1:00-23:00；离线兜底回呼 Ticket）
  - CONTEXT.md › 转接（触发后会话进入 Handed-off，坐席主导，助理退至后台）
  - CONTEXT.md › 审计日志（Handoff 发起与结束须留痕）
  - issue #17 验收标准4/5

设计约定：
  - is_in_service_time / all_agents_busy 为纯判定（now 可注入，测试验证边界）。
  - trigger_handoff 为执行入口：正常转接（服务时间 + 有在线坐席）→ 会话转 handed_off
    进入待接入队列；离线兜底（非服务时间 或 全忙超阈值）→ 额外创建回呼请求 Ticket
    派单到 Skill Group。两种路径会话均流转 handed_off（不置 closed = 不强制结束）。
  - WS handoff.start 推送在 ws 模块（service 不感知传输层，调用方负责）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.conversation.service import transition_conversation_state
from app.handoff.triggers import HandoffReason
from app.models import Conversation, Ticket, User
from app.models.ticket import TicketStatus, TicketType
from app.ticket.service import create_ticket, transition_ticket_status

#: 坐席服务时间：1:00-23:00（半开区间 [start_hour, end_hour)，CONTEXT › 服务时间与离线兜底）。
AGENT_SERVICE_START_HOUR = 1
AGENT_SERVICE_END_HOUR = 23

#: 回呼请求 Ticket 内容前缀（CONTEXT › 离线兜底：创建 Ticket(类型:回呼请求)）。
CALLBACK_TICKET_CONTENT_PREFIX = "[回呼请求]"

#: 默认派单技能组（CONTEXT › 技能组：套餐业务组/故障报修组/投诉处理组）。
DEFAULT_SKILL_GROUP = "套餐业务组"


def is_in_service_time(now: datetime | None = None) -> bool:
    """坐席服务时间判定：1:00 ≤ hour < 23:00。

    now 缺省取本地时间（部署为本地裸机 Windows / Asia/Shanghai，PRD › 部署）；
    测试注入 now 验证边界。
    """
    moment = now or datetime.now()
    return AGENT_SERVICE_START_HOUR <= moment.hour < AGENT_SERVICE_END_HOUR


def all_agents_busy(db: Session) -> bool:
    """全忙判定：无在线坐席（status=online 计数为 0）即「忙线超阈值」。

    坐席状态三态 online/offline/break（US-30）；在线坐席为 0 时无法接入
    任何 Handoff 会话，触发离线兜底（CONTEXT › 离线兜底）。
    """
    online = db.execute(select(User).where(User.status == "online")).scalars().all()
    return len(online) == 0


@dataclass
class HandoffOutcome:
    """触发执行结果。offline_fallback=True 时已创建回呼请求 Ticket 并派单。"""

    conversation_id: int
    reason: HandoffReason
    offline_fallback: bool
    ticket_id: int | None = None


def trigger_handoff(
    db: Session,
    conversation: Conversation,
    reason: HandoffReason | str,
    *,
    skill_group: str | None = None,
    now: datetime | None = None,
) -> HandoffOutcome:
    """触发 Handoff：按服务时间与坐席可用性路由执行。

    正常转接（服务时间内且有在线坐席）：
      会话 → handed_off（进入待接入队列，US-20），WS handoff.start 由调用方推送。
    离线兜底（非服务时间 或 全忙超阈值，CONTEXT › 离线兜底）：
      创建回呼请求 Ticket 并派单到 Skill Group；会话仍流转 handed_off
      （进入待接入队列，次日服务时间坐席接入）——不置 closed（不强制结束会话）。

    审计：写入 handoff.start（CONTEXT › 审计日志：Handoff 发起）。
    """
    from app.auth.audit import write_audit_log

    reason_enum = reason if isinstance(reason, HandoffReason) else HandoffReason(reason)

    offline = (not is_in_service_time(now)) or all_agents_busy(db)
    ticket: Ticket | None = None
    if offline:
        ticket = create_callback_ticket(db, conversation, reason_enum, skill_group)

    if conversation.status != "handed_off":
        transition_conversation_state(db, conversation, "handed_off")
    db.commit()
    db.refresh(conversation)
    if ticket is not None:
        db.refresh(ticket)

    detail: dict[str, object] = {
        "conversation_id": conversation.id,
        "reason": reason_enum.value,
        "offline_fallback": offline,
    }
    if ticket is not None:
        detail["ticket_id"] = ticket.id
        detail["skill_group"] = ticket.skill_group
    write_audit_log(
        db,
        actor_type="assistant",
        action="handoff.start",
        detail=detail,
    )

    return HandoffOutcome(
        conversation_id=conversation.id,
        reason=reason_enum,
        offline_fallback=offline,
        ticket_id=ticket.id if ticket is not None else None,
    )


def create_callback_ticket(
    db: Session,
    conversation: Conversation,
    reason: HandoffReason,
    skill_group: str | None = None,
) -> Ticket:
    """创建回呼请求 Ticket（工单类）并派单到 Skill Group（CONTEXT › 离线兜底）。

    内容模板「[回呼请求] 转接原因：… — 坐席将在服务时间联系您」；创建后立即派单
    （pending → dispatched），skill_group 标注目标技能组。审计 handoff.offline_callback
    记录 Ticket 与技能组（调用方在 commit 后由本函数内提交）。
    """
    from app.auth.audit import write_audit_log

    target_group = skill_group or DEFAULT_SKILL_GROUP
    ticket = create_ticket(
        db,
        conversation_id=conversation.id,
        ticket_type=TicketType.TICKETING.value,
        content=(
            f"{CALLBACK_TICKET_CONTENT_PREFIX} 转接原因：{reason.value} — 坐席将在服务时间联系您"
        ),
        creator_type="assistant",
        customer_id=conversation.customer_id,
    )
    ticket.skill_group = target_group
    transition_ticket_status(db, ticket, TicketStatus.DISPATCHED.value)
    write_audit_log(
        db,
        actor_type="assistant",
        action="handoff.offline_callback",
        detail={
            "conversation_id": conversation.id,
            "ticket_id": ticket.id,
            "skill_group": target_group,
            "reason": reason.value,
        },
    )
    return ticket
