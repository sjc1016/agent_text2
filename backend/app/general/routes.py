"""通用咨询 REST 路由（Visitor 免认证，US-1）。

PRD 依据：
  - 实现决策 › API 契约（/general-info/* 通用咨询）
  - 实现决策 › 知识来源（结构化数据 + RAG 文档检索）
  - CONTEXT.md › 业务能力 / 通用咨询类：无需认证，Visitor 即可查询公开信息
  - 用户故事 US-1

设计说明（与 tool 调用 seam 对称）：
  - 端点直接复用 general.service 的查询函数，不重复实现检索/过滤逻辑；
  - 不挂任何鉴权依赖（无 CurrentCustomer），即「免认证」边界；
  - 响应模型 from_attributes 直出 ORM 对象，与 conversation schemas 一致。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.general.schemas import (
    BusinessHallOut,
    CoverageAreaOut,
    KnowledgeDocumentOut,
    PlanOut,
)
from app.general.service import (
    query_coverage,
    query_halls,
    query_plans,
    search_rag,
)
from app.models import BusinessHall, CoverageArea, KnowledgeDocument, Plan

router = APIRouter(prefix="/general-info", tags=["general-info"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/search", response_model=list[KnowledgeDocumentOut])
def search(query: str, db: DbSession, k: int = 3) -> list[KnowledgeDocument]:
    """RAG 检索知识库（政策/规则/手册）；无匹配返回空列表（不编造）。"""
    return search_rag(db, query, k=max(1, k))


@router.get("/plans", response_model=list[PlanOut])
def plans(
    db: DbSession,
    names: list[str] | None = None,
    name: str | None = None,
) -> list[Plan]:
    """套餐目录查询（结构化数据）：?names=a&names=b 或 ?name=x 过滤。"""
    selected = names or ([name] if name else None)
    return query_plans(db, names=selected)


@router.get("/coverage", response_model=list[CoverageAreaOut])
def coverage(area: str, db: DbSession) -> list[CoverageArea]:
    """网络覆盖查询（结构化数据）：按区域名模糊匹配。"""
    return query_coverage(db, area)


@router.get("/halls", response_model=list[BusinessHallOut])
def halls(district: str, db: DbSession) -> list[BusinessHall]:
    """营业厅查询（结构化数据）：按行政区过滤。"""
    return query_halls(db, district)
