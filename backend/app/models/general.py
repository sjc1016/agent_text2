"""通用咨询领域模型（知识文档 RAG + 结构化参考数据）。

PRD 依据：
  - CONTEXT.md › 知识来源：结构化数据（DB 套餐目录、营业厅列表、资费表）+
    非结构化文档（RAG 政策/规则/手册，sqlite-vec 向量检索）
  - CONTEXT.md › 业务能力 / 通用咨询类：无需认证，Visitor 即可查询
  - 用户故事 US-1

向量表说明：knowledge_vec（vec0 虚拟表）不在此声明——sqlite-vec 虚拟表
不经 SQLAlchemy metadata（create_all 不覆盖），由 Alembic 迁移 0006 管理
（验收标准4：upgrade/downgrade 可逆）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KnowledgeDocument(Base):
    """非结构化知识文档（政策/规则/手册），向量索引存于 knowledge_vec 虚拟表。

    vec0 虚拟表的 rowid 即本表 id（索引入库时回填），检索时按 id join 原文。
    """

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String, nullable=False)  # policy/rule/manual
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Plan(Base):
    """套餐目录（结构化数据 / 资费表）：套餐介绍与对比（US-1）。"""

    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)  # 月费（元）
    data_allowance: Mapped[str | None] = mapped_column(String, nullable=True)  # 流量
    call_minutes: Mapped[str | None] = mapped_column(String, nullable=True)  # 通话
    description: Mapped[str | None] = mapped_column(String, nullable=True)


class CoverageArea(Base):
    """网络覆盖区域（结构化数据）：4G/5G 覆盖等级（US-1）。"""

    __tablename__ = "coverage_areas"

    id: Mapped[int] = mapped_column(primary_key=True)
    area: Mapped[str] = mapped_column(String, nullable=False)  # 区域名
    network_type: Mapped[str] = mapped_column(String, nullable=False)  # 4G/5G
    level: Mapped[str] = mapped_column(String, nullable=False)  # full/partial/none


class BusinessHall(Base):
    """营业厅列表（结构化数据）：地址查询（US-1）。"""

    __tablename__ = "business_halls"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    district: Mapped[str] = mapped_column(String, nullable=False)  # 行政区
    address: Mapped[str] = mapped_column(String, nullable=False)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    business_hours: Mapped[str | None] = mapped_column(String, nullable=True)
