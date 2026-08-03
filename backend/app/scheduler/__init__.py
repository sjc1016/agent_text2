"""B10 调度任务模块（APScheduler 进程内调度 + SQLite 持久化）。

PRD 依据：实现决策 › 任务调度；测试决策 › 调度任务 seam（直接调用 job 函数，
不启调度器）。job 函数均为 async，便于在 uvicorn 单进程事件循环内推送 WS 事件；
调度器注册与启动见 setup.py（build_scheduler / start_scheduler）。
"""
