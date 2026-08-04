"""B10 调度器配置就绪测试（issue #19 验收5：APScheduler SQLite 持久化配置就绪，job 可恢复）。

PRD 依据：实现决策 › 任务调度（APScheduler 进程内调度 + SQLite 持久化）；
测试决策 › 调度任务 seam（不启调度器，直接验证配置对象）。

#66 修复：_run_job 为签名含 keyword-only now 的 job 注入当前时间（APScheduler
不会自动注入触发时间，注册处也未持有时间来源 → close_timed_out_sessions 缺 now
每分钟 TypeError，超时会话回收失效）。
"""

from datetime import datetime

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


class TestRunJobInjectsNow:
    """#66：_run_job 为签名含 keyword-only now 的 job 注入当前时间。

    APScheduler 触发时不自动传入 scheduled_run_time；注册处也未持有时间来源。
    _run_job 需检测目标函数签名是否含 now 参数，含则注入 datetime.now()。
    """

    async def test_injects_now_for_function_requiring_it(self, monkeypatch):
        from types import SimpleNamespace

        from app.scheduler import setup

        monkeypatch.setattr(setup, "SessionLocal", lambda: SimpleNamespace(close=lambda: None))

        captured: dict = {}

        async def needs_now(db, *, now: datetime):
            captured["now"] = now
            return "ok"

        result = await setup._run_job(needs_now)

        assert result == "ok"
        assert isinstance(captured["now"], datetime)

    async def test_does_not_inject_now_for_function_not_requiring_it(self, monkeypatch):
        from types import SimpleNamespace

        from app.scheduler import setup

        monkeypatch.setattr(setup, "SessionLocal", lambda: SimpleNamespace(close=lambda: None))

        async def no_now(db, **kwargs):
            return kwargs

        result = await setup._run_job(no_now, timeout_minutes=30)

        assert result == {"timeout_minutes": 30}


class TestRunJobClosesTimedOutSessionsEndToEnd:
    """#66 端到端：注册的 close_timed_out_sessions job 经 _run_job 触发成功关闭
    超时会话（ended_at 落位）。

    修复前 _run_job 不注入 now → close_timed_out_sessions 每分钟 TypeError，
    超时会话回收从未执行。本测试走真实 job 函数 + 临时 DB，验证回收链路打通。
    """

    async def test_run_job_closes_stale_session(self, tmp_path, monkeypatch):
        from sqlalchemy.orm import sessionmaker

        from app.db import create_engine
        from app.models import Base, Conversation, Customer
        from app.models import Session as SessionRecord
        from app.scheduler import setup
        from app.scheduler.jobs import close_timed_out_sessions

        url = f"sqlite:///{tmp_path / 'e2e.db'}"
        engine = create_engine(url)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)

        # 播种：客户 + 会话 + 一个远超 timeout 的活跃 Session
        seed = factory()
        customer = Customer(phone="13800000999", service_password_hash="x")
        seed.add(customer)
        seed.commit()
        conv = Conversation(customer_id=customer.id, status="authenticated")
        seed.add(conv)
        seed.commit()
        stale = SessionRecord(conversation_id=conv.id, started_at=datetime(2026, 1, 1, 8, 0))
        seed.add(stale)
        seed.commit()
        stale_id = stale.id
        seed.close()

        # _run_job 每次新建 session —— 指向同一临时库（模拟调度器运行时）
        monkeypatch.setattr(setup, "SessionLocal", factory)

        closed = await setup._run_job(close_timed_out_sessions, timeout_minutes=30)

        assert closed == 1
        check = factory()
        refreshed = check.get(SessionRecord, stale_id)
        assert refreshed is not None
        assert refreshed.ended_at is not None  # 超时会话已被关闭
        check.close()
        engine.dispose()
