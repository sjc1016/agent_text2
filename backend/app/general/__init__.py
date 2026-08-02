"""B4 通用咨询模块（RAG 知识检索 + 结构化数据查询，Visitor 免认证）。"""

from app.general.service import (
    CREATE_VEC_TABLE_SQL,
    index_knowledge_document,
    query_coverage,
    query_halls,
    query_plans,
    search_rag,
)

__all__ = [
    "CREATE_VEC_TABLE_SQL",
    "index_knowledge_document",
    "query_coverage",
    "query_halls",
    "query_plans",
    "search_rag",
]
