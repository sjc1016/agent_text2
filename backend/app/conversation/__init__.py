"""会话与消息模块。

B2 循环2：REST /conversations（列表）、/conversations/{id}/messages（历史）。
模块边界（PRD › 实现决策 › 模块划分）：conversation 承担会话与消息读写，
状态机流转在循环6 补全，WS 事件由 ws 模块推送。
"""
