"""B10 调度器装配：APScheduler AsyncIOScheduler + SQLAlchemyJobStore（SQLite 持久化）。

PRD 依据：实现决策 › 任务调度（进程内调度 + SQLite 持久化）；部署（uvicorn 单
进程手动启动）。build_scheduler 纯构建（可测，不启动）；start_scheduler 供应用
入口（FastAPI lifespan）在 uvicorn 单进程事件循环内启动，job 持久化可恢复。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings
from app.db import SessionLocal
from app.scheduler.jobs import (
    close_timed_out_sessions,
    dispatch_callback_tickets,
    monitor_agent_availability,
    trigger_pending_transaction_reauth,
)

#: 本地部署时区（Asia/Shanghai，PRD › 部署；job 触发调度以此为基准）
_SCHEDULER_TIMEZONE = "Asia/Shanghai"

#: 4 类 job 运行间隔（分钟）——按业务时效性配置（PRD › 任务调度）
_JOB_INTERVALS_MINUTES: dict[str, int] = {
    "trigger_pending_transaction_reauth": 1,
    "close_timed_out_sessions": 1,
    "monitor_agent_availability": 5,
    "dispatch_callback_tickets": 10,
}

#: job 注册表（id → 函数），与验收标准 4 类 job 一一对应
_JOB_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "trigger_pending_transaction_reauth": trigger_pending_transaction_reauth,
    "close_timed_out_sessions": close_timed_out_sessions,
    "monitor_agent_availability": monitor_agent_availability,
    "dispatch_callback_tickets": dispatch_callback_tickets,
}


async def _run_job(func: Callable[..., Any], **kwargs: Any) -> Any:
    """job 执行包装器：每次执行新建 DB session（调度无请求上下文），用后关闭。"""
    db = SessionLocal()
    try:
        return await func(db, **kwargs)
    finally:
        db.close()


def build_scheduler(jobstore_url: str | None = None) -> AsyncIOScheduler:
    """构建调度器配置（不启动）：SQLAlchemyJobStore(SQLite) + 注册 4 类 job。

    jobstore_url 缺省取应用 database_url（Settings）；测试注入临时库验证持久化
    恢复。add_job 同步持久化到 store（重启后由 store 恢复），幂等 replace_existing。
    """
    settings = get_settings()
    url = jobstore_url or settings.database_url
    scheduler = AsyncIOScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=url)},
        timezone=_SCHEDULER_TIMEZONE,
    )

    timeout = settings.session_timeout_minutes
    for job_id, func in _JOB_FUNCTIONS.items():
        kwargs: dict[str, Any] = {}
        if job_id == "close_timed_out_sessions":
            kwargs["timeout_minutes"] = timeout
        scheduler.add_job(
            _run_job,
            "interval",
            minutes=_JOB_INTERVALS_MINUTES[job_id],
            id=job_id,
            args=[func],
            kwargs=kwargs,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
    return scheduler


_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> AsyncIOScheduler:
    """启动调度器（进程内，幂等）：供 FastAPI lifespan 在 uvicorn 单进程内调用。"""
    global _scheduler
    if _scheduler is None:
        _scheduler = build_scheduler()
        _scheduler.start()
    return _scheduler


def shutdown_scheduler() -> None:
    """停止调度器（应用退出时调用，wakeup 后等待当前 job 结束）。"""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=True)
        _scheduler = None
