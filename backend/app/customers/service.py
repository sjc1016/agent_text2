"""客户侧业务逻辑（深模块：通知查询封装在服务层）。

PRD 依据：
  - 实现决策 › API 契约 /customers/me、/notifications（RESTful 端点）
  - 测试决策 › HTTP 集成 seam
  - 用户故事 US-14（站内通知）、US-17（账号信息）
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Notification


def list_customer_notifications(db: Session, customer_id: int) -> list[Notification]:
    """返回当前客户站内通知列表（US-14），按创建时间倒序（新通知在前）。

    同 created_at 按 id 倒序（时间戳粒度不足时排序稳定）；read 未读标记
    原样返回，前端预览条自行 filter（不在此裁减已读）。
    """
    stmt = (
        select(Notification)
        .where(Notification.customer_id == customer_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    )
    return list(db.execute(stmt).scalars().all())
