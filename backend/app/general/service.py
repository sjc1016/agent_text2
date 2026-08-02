"""B4 通用咨询服务（深模块：RAG 检索 + 结构化查询，隐藏 sqlite-vec 细节）。

PRD 依据：
  - 实现决策 › 知识来源（结构化数据 + 非结构化文档 RAG，sqlite-vec 向量检索）
  - 测试决策 › tool 调用 seam（RAG 检索纯函数，与 LLM 解耦）
  - 验收标准1：检索返回政策/规则/手册内容，不编造
  - 验收标准2：套餐/覆盖/营业厅结构化查询
  - 验收标准4：向量 schema 经 Alembic 迁移管理（0006）

设计说明（深模块）：
  - 对外接口小：index_knowledge_document / search_rag / query_*；
  - 内部封装：确定性嵌入、vec0 虚拟表 MATCH、距离阈值过滤（不编造）、
    结构化表查询；调用方不感知 sqlite-vec。
  - 向量表 knowledge_vec 的 rowid 与 knowledge_documents.id 一一对应。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.general.embedding import EMBEDDING_DIM, embed_text
from app.models.general import (
    BusinessHall,
    CoverageArea,
    KnowledgeDocument,
    Plan,
)

#: vec0 虚拟表名（rowid ↔ knowledge_documents.id）
VEC_TABLE = "knowledge_vec"

#: 建表 SQL（迁移 0006 与测试 fixture 共用，保证 schema 一致）
CREATE_VEC_TABLE_SQL = (
    f"CREATE VIRTUAL TABLE {VEC_TABLE} USING vec0(embedding float[{EMBEDDING_DIM}])"
)

#: 检索距离阈值：单位向量距离 > 阈值视为不相关（不编造：拒绝返回无关文档）
DISTANCE_THRESHOLD = 1.2


def index_knowledge_document(
    db: Session, *, category: str, title: str, content: str
) -> KnowledgeDocument:
    """入库知识文档并写入向量索引（不编造的前提：检索只返回入库原文）。

    向 knowledge_vec 写 rowid=doc.id 的向量；rowid 由 flush 后取主键回填。
    """
    doc = KnowledgeDocument(category=category, title=title, content=content)
    db.add(doc)
    db.flush()  # 取 doc.id
    blob = embed_text(f"{title}\n{content}")
    db.execute(
        sa.text(f"INSERT INTO {VEC_TABLE}(rowid, embedding) VALUES (:rid, :emb)"),
        {"rid": doc.id, "emb": blob},
    )
    db.commit()
    db.refresh(doc)
    return doc


def search_rag(db: Session, query: str, k: int = 3) -> list[KnowledgeDocument]:
    """向量检索 top-k 相关知识文档（按距离升序），不相关（超阈值）一律过滤。

    不编造（验收标准1）：返回内容全部来自 knowledge_documents 原文；
    无匹配返回空列表，由调用方（tool）给出诚实回复。
    """
    query = (query or "").strip()
    if not query:
        return []
    blob = embed_text(query)
    rows = db.execute(
        sa.text(f"SELECT rowid, distance FROM {VEC_TABLE} WHERE embedding MATCH :emb AND k = :k"),
        {"emb": blob, "k": max(1, k)},
    ).fetchall()
    hits = [
        (row[0], row[1])
        for row in rows
        if row[1] is not None and float(row[1]) <= DISTANCE_THRESHOLD
    ]
    if not hits:
        return []
    ids = [hit[0] for hit in hits]
    docs = (
        db.execute(sa.select(KnowledgeDocument).where(KnowledgeDocument.id.in_(ids)))
        .scalars()
        .all()
    )
    order = {doc_id: idx for idx, (doc_id, _dist) in enumerate(hits)}
    return sorted(docs, key=lambda d: order[d.id])


def query_plans(db: Session, names: list[str] | None = None) -> list[Plan]:
    """套餐目录查询（结构化数据）：按名称过滤，返回匹配套餐（US-1）。"""
    stmt = sa.select(Plan).order_by(Plan.id)
    if names:
        stmt = stmt.where(Plan.name.in_(names))
    return list(db.execute(stmt).scalars().all())


def query_coverage(db: Session, area: str) -> list[CoverageArea]:
    """网络覆盖查询（结构化数据）：按区域名模糊匹配（US-1）。"""
    if not area.strip():
        return []
    return list(
        db.execute(
            sa.select(CoverageArea)
            .where(CoverageArea.area.like(f"%{area.strip()}%"))
            .order_by(CoverageArea.id)
        )
        .scalars()
        .all()
    )


def query_halls(db: Session, district: str) -> list[BusinessHall]:
    """营业厅查询（结构化数据）：按行政区过滤（US-1）。"""
    if not district.strip():
        return []
    return list(
        db.execute(
            sa.select(BusinessHall)
            .where(BusinessHall.district.like(f"%{district.strip()}%"))
            .order_by(BusinessHall.id)
        )
        .scalars()
        .all()
    )
