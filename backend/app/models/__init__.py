"""ORM 模型聚合。

集中导出所有模型，供 Alembic env.py（Base.metadata）与业务模块 import。
"""

from app.models.audit import AuditLog
from app.models.base import Base
from app.models.conversation import Conversation, Message, Session
from app.models.customers import Customer
from app.models.general import (
    BusinessHall,
    CoverageArea,
    KnowledgeDocument,
    Plan,
)
from app.models.inquiry import CustomerAccount, CustomerValueAddedService
from app.models.ticket import Notification, Ticket
from app.models.users import User

__all__ = [
    "Base",
    "Customer",
    "User",
    "AuditLog",
    "Conversation",
    "Session",
    "Message",
    "Ticket",
    "Notification",
    "KnowledgeDocument",
    "Plan",
    "CoverageArea",
    "BusinessHall",
    "CustomerAccount",
    "CustomerValueAddedService",
]
