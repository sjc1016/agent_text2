"""通用咨询 REST 响应 schema（Pydantic）。

PRD 依据：实现决策 › API 契约（/general-info/* 通用咨询）；
ORM → Pydantic 经 from_attributes（SQLAlchemy 2.0 模型直出，与 conversation schemas 一致）。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class KnowledgeDocumentOut(BaseModel):
    """RAG 检索结果（知识库原文，不编造）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    title: str
    content: str


class PlanOut(BaseModel):
    """套餐目录项（结构化数据 / 资费表）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    price: float
    data_allowance: str | None
    call_minutes: str | None
    description: str | None


class CoverageAreaOut(BaseModel):
    """网络覆盖项（4G/5G 覆盖等级）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    area: str
    network_type: str
    level: str


class BusinessHallOut(BaseModel):
    """营业厅项（名称/行政区/地址/营业时间）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    district: str
    address: str
    phone: str | None
    business_hours: str | None
