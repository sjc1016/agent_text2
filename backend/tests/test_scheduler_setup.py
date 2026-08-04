"""B10 调度器配置就绪测试（issue #19 验收5：APScheduler SQLite 持久化配置就绪，job 可恢复）。

PRD 依据：实现决策 › 任务调度（APScheduler 进程内调度 + SQLite 持久化）；
测试决策 › 调度任务 seam（不启调度器，直接验证配置对象）。
"""

from datetime import datetime

from app.scheduler.setup import _run_job, build_scheduler

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


class TestRunJobNowInjection:
    """issue #66：_run_job 触发链路为需 `now` 的 job 注入当前时间。

    回归背景：close_timed_out_sessions 签名要求 keyword-only `now`，注册处只传
    timeout_minutes → 每分钟触发 TypeError、超时会话回收从未执行。
    """

    class _FakeSession:
        """仅需 close 语义的假 session（_run_job 用完关闭）。"""

        def close(self) -> None:
            return None

    async def test_injects_now_for_now_requiring_job(self, monkeypatch):
        """目标函数签名含 `now` → _run_job 注入当前 datetime，其余 kwargs 透传。"""
        captured: dict = {}

        async def target(db, *, now, timeout_minutes):
            captured["now"] = now
            captured["timeout_minutes"] = timeout_minutes
            return 3

        # 不落库的假 session：验证注入行为，避免依赖真实 DB
        monkeypatch.setattr("app.scheduler.setup.SessionLocal", lambda: self._FakeSession())
        result = await _run_job(target, timeout_minutes=30)

        assert result == 3
        assert isinstance(captured["now"], datetime)
        assert captured["timeout_minutes"] == 30

    async def test_does_not_inject_now_for_plain_job(self, monkeypatch):
        """目标函数不接收 `now` → 不多传参数（其余 job 保持原签名调用）。"""
        monkeypatch.setattr("app.scheduler.setup.SessionLocal", lambda: self._FakeSession())

        async def target(db):
            return 0

        assert await _run_job(target) == 0

    async def test_registered_close_timed_out_sessions_job_closes_expired_session(
        self, tmp_path, db, monkeypatch
    ):
        """端到端：注册后的 close_timed_out_sessions job 经 _run_job 触发成功回收超时会话。

        直接调用持久化 job 的可执行体（job.func = _run_job + args/kwargs），并把
        SessionLocal 指到测试库——修复前此处抛 TypeError: missing 'now'，且会话
        永远不被关闭（issue #66 回归）。
        """
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.auth.security import hash_password
        from app.models import Conversation, Customer
        from app.models import Session as SessionRecord
        from app.scheduler import setup as scheduler_setup

        monkeypatch.setattr(scheduler_setup, "SessionLocal", lambda: db)

        customer = Customer(phone="13800000666", service_password_hash=hash_password("x"))
        db.add(customer)
        db.flush()
        conv = Conversation(customer_id=customer.id, status="authenticated")
        db.add(conv)
        db.flush()
        expired = SessionRecord(conversation_id=conv.id, started_at=datetime(2026, 1, 1, 8, 0))
        db.add(expired)
        db.commit()
        session_id = expired.id

        url = f"sqlite:///{tmp_path / 'scheduler.db'}"
        scheduler = build_scheduler(jobstore_url=url)
        try:
            job = scheduler.get_job("close_timed_out_sessions")
            assert job is not None
            closed = await job.func(*job.args, **job.kwargs)
            assert closed == 1
        finally:
            _close(scheduler)

        # job 内 db.close() 已关闭 fixture session → 新开会话验证落库结果
        engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
        with sessionmaker(bind=engine)() as verify:
            record = verify.get(SessionRecord, session_id)
            assert record is not None
            assert record.ended_at is not None  # 超时会话已关闭（ended_at 落位）
        engine.dispose()
