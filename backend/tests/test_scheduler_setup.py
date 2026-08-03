"""B10 调度器配置就绪测试（issue #19 验收5：APScheduler SQLite 持久化配置就绪，job 可恢复）。

PRD 依据：实现决策 › 任务调度（APScheduler 进程内调度 + SQLite 持久化）；
测试决策 › 调度任务 seam（不启调度器，直接验证配置对象）。
"""

from app.scheduler.setup import build_scheduler

#: 4 类 job 注册 id（与实现决策 › 任务调度 一一对应）
EXPECTED_JOB_IDS = frozenset(
    {
        "trigger_pending_transaction_reauth",
        "close_timed_out_sessions",
        "monitor_agent_availability",
        "dispatch_callback_tickets",
    }
)


def _close(scheduler) -> None:
    """关闭未启动的调度器（shutdown 未运行调度器会抛 SchedulerNotRunningError）。"""
    if scheduler.running:
        scheduler.shutdown(wait=False)


def test_build_scheduler_registers_all_four_jobs(tmp_path):
    url = f"sqlite:///{tmp_path / 'scheduler.db'}"
    scheduler = build_scheduler(jobstore_url=url)
    try:
        assert not scheduler.running  # 配置就绪但不启动（手动启动契约）
        jobs = scheduler.get_jobs()
        assert {job.id for job in jobs} == EXPECTED_JOB_IDS
        assert all(job.trigger is not None for job in jobs)
    finally:
        _close(scheduler)


async def test_jobs_persisted_and_recoverable_from_sqlite(tmp_path):
    """验收5：SQLite 持久化 + job 可恢复。

    首次构建并 start（建表 + 持久化 job）后关闭；重新构建同一库（模拟重启），
    job 从 SQLite jobstore 恢复。
    """
    url = f"sqlite:///{tmp_path / 'scheduler.db'}"

    first = build_scheduler(jobstore_url=url)
    first.start()  # 进程内调度：持久化 job 到 SQLite
    assert first.running
    first.shutdown(wait=False)

    second = build_scheduler(jobstore_url=url)
    try:
        assert not second.running
        restored = {job.id for job in second.get_jobs()}
        assert restored == EXPECTED_JOB_IDS
    finally:
        _close(second)
