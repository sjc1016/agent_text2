"""B10 调度任务 job 函数（issue #19）。

PRD 依据：实现决策 › 任务调度（4 类 job：Ticket 复核触发 / 会话超时 / 坐席状态
监控 / 离线兜底回呼 Ticket 派单）；测试决策 › 调度任务 seam —— 测试直接调用
job 函数（不启调度器），验证状态机流转与副作用。

约定：
  - job 函数接收 db: Session（调度器包装每次新建，测试注入临时 session）；
    内部负责 commit（调度环境无请求级事务）。
  - 推送类副作用经 ws.hub 静默跳过（目标未连接时不抛错，推送非业务主路径）。
  - 审计统一 actor_type="system"（调度无用户主体，模型注释允许 customer/agent/system）。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, Customer, Ticket, User
from app.models import Session as SessionRecord
from app.models.ticket import TicketStatus, TicketType
from app.ticket.service import transition_ticket_status


async def dispatch_callback_tickets(db: Session) -> int:
    """离线兜底回呼 Ticket 派单 job（US-29）：pending 回呼 → 派单到 Skill Group。

    CONTEXT › 离线兜底：回呼请求 Ticket 派单到对应 Skill Group。创建时已实时派单
    （B8 create_callback_ticket），本 job 为周期性补漏兜底——确保 content 以
    [回呼请求] 开头的工单类 Ticket 均已派单（pending → dispatched），幂等：
    已派单/非回呼 Ticket 不动。
    """
    from app.handoff.service import CALLBACK_TICKET_CONTENT_PREFIX, DEFAULT_SKILL_GROUP

    tickets = (
        db.execute(
            select(Ticket).where(
                Ticket.ticket_type == TicketType.TICKETING,
                Ticket.status == TicketStatus.PENDING,
                Ticket.content.like(f"{CALLBACK_TICKET_CONTENT_PREFIX}%"),
            )
        )
        .scalars()
        .all()
    )
    for ticket in tickets:
        transition_ticket_status(db, ticket, TicketStatus.DISPATCHED.value)
        if ticket.skill_group is None:
            ticket.skill_group = DEFAULT_SKILL_GROUP
    db.commit()
    return len(tickets)


async def close_timed_out_sessions(db: Session, *, now: datetime, timeout_minutes: int) -> int:
    """会话超时检测 job（US-18）：活跃 Session 闲置超时 → 断开（ended_at 落位）。

    CONTEXT › 会话片段：Session 一段连续活跃交互，超时后断开；重新交互开启新
    Session（ensure_active_session），归属同一 Conversation。
    """
    cutoff = now - timedelta(minutes=timeout_minutes)
    sessions = (
        db.execute(
            select(SessionRecord).where(
                SessionRecord.ended_at.is_(None),
                SessionRecord.started_at < cutoff,
            )
        )
        .scalars()
        .all()
    )
    for record in sessions:
        record.ended_at = now
    db.commit()
    return len(sessions)


async def ensure_active_session(
    db: Session, conversation: Conversation, *, now: datetime, timeout_minutes: int
) -> SessionRecord:
    """交互入口维护会话片段：返回该 Conversation 的当前活跃 Session（US-18）。

    CONTEXT › 会话片段：超时后断开，重新交互开启新 Session，归属同一 Conversation。
      - 无活跃 Session → 新建（started_at=now）；
      - 活跃 Session 未超时 → 原样返回（不新建）；
      - 活跃 Session 已超时 → 关闭旧 Session（ended_at=now）并新建。
    供交互入口（消息收发）在用户重新交互时调用，保证新 Session 归属原 Conversation。
    """
    active = db.execute(
        select(SessionRecord).where(
            SessionRecord.conversation_id == conversation.id,
            SessionRecord.ended_at.is_(None),
        )
    ).scalar_one_or_none()

    if active is not None and active.started_at >= now - timedelta(minutes=timeout_minutes):
        return active

    if active is not None:
        active.ended_at = now
    current = SessionRecord(conversation_id=conversation.id, started_at=now)
    db.add(current)
    db.commit()
    return current


async def monitor_agent_availability(db: Session) -> dict:
    """坐席状态监控 job：统计在线坐席，全忙（无在线）时写审计告警留痕。

    CONTEXT › 离线兜底：无在线坐席（全忙超阈值）时进入离线兜底。job 周期性
    监控在线坐席数量，全忙写 agent.availability.alert 审计供追溯。
    """
    from app.auth.audit import write_audit_log

    online = db.execute(select(User).where(User.status == "online")).scalars().all()
    count = len(online)
    all_busy = count == 0
    if all_busy:
        write_audit_log(
            db,
            actor_type="system",
            action="agent.availability.alert",
            detail={"online_agents": count, "all_busy": True},
        )
    return {"online_agents": count, "all_busy": all_busy}


async def trigger_pending_transaction_reauth(db: Session) -> int:
    """Ticket 待执行→执行中触发服务密码复核 job（US-12）。

    CONTEXT › 办理执行复核：办理类 Ticket 从「待执行」进入「执行中」前必须再次
    验证服务密码。job 扫描待执行（pending）办理类 Ticket，经
    trigger_execution_reauth 校验通过后推送 reauth.required（WS）并写审计，
    提示用户经 /auth/reauth 复核取得 execute_token 后再执行（状态保持 pending）。
    无客户主体的办理 Ticket 跳过（Visitor 不发起办理，防御）。
    """
    from app.auth.audit import write_audit_log
    from app.transaction.service import trigger_execution_reauth
    from app.ws.hub import push_reauth_required

    tickets = (
        db.execute(
            select(Ticket).where(
                Ticket.ticket_type == TicketType.TRANSACTION,
                Ticket.status == TicketStatus.PENDING,
            )
        )
        .scalars()
        .all()
    )
    triggered = 0
    for ticket in tickets:
        if ticket.customer_id is None:
            continue
        customer = db.get(Customer, ticket.customer_id)
        if customer is None:
            continue
        try:
            trigger_execution_reauth(db, customer, ticket)
        except ValueError:
            continue  # 状态/归属不满足 → 跳过（job 幂等，异常不中断批量）
        write_audit_log(
            db,
            actor_type="system",
            action="transaction.reauth_request",
            detail={"ticket_id": ticket.id},
        )
        await push_reauth_required(ticket)
        triggered += 1
    db.commit()
    return triggered
