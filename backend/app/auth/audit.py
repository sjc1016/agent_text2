"""审计日志写入辅助。

PRD/CONTEXT 依据：CONTEXT.md › 审计日志；ADR 0004。
记录服务密码认证（成功/失败）、敏感数据访问等关键操作，供合规留痕与追溯。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def write_audit_log(
    db: Session,
    *,
    actor_type: str,
    action: str,
    actor_id: int | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """写入一条审计日志并提交。"""
    log = AuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        detail=detail,
    )
    db.add(log)
    db.commit()
