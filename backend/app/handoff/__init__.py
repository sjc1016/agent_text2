"""转接 Handoff 模块（B8，issue #17）。

CONTEXT › 转接：助理将会话移交给坐席；触发后坐席主导，助理退至后台协助。
模块划分（PRD 实现决策 › 模块划分）：handoff 模块承载触发评估（triggers）与
执行决策（service，含服务时间/离线兜底），WS 推送在 ws 模块（解耦）。
"""
