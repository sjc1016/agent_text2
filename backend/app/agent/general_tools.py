"""B4 通用咨询 tools（注册进 ToolRegistry，供 Assistant 对话流调用）。

PRD 依据：
  - 实现决策 › 知识来源（结构化数据 + RAG 文档检索）
  - 测试决策 › tool 调用 seam（通用咨询类 RAG 检索，纯函数与 LLM 解耦）
  - 验收标准1：RAG 检索返回政策/规则/手册内容，不编造
  - 验收标准2：套餐介绍与对比、网络覆盖、营业厅地址结构化查询
  - 用户故事 US-1（Visitor 免认证咨询公开信息）

DB 依赖：ToolContext.db 由调用方（WS 路由 / 测试）注入，tool 保持可测纯函数。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agent.tools import ToolContext, ToolRegistry, tool
from app.general.service import (
    index_knowledge_document,  # noqa: F401 - 知识库维护入口（管理/种子场景）
    query_coverage,
    query_halls,
    query_plans,
    search_rag,
)


def _require_db(ctx: ToolContext) -> Session:
    if ctx.db is None:
        raise RuntimeError("通用咨询 tool 需要 ToolContext.db（数据库会话）")
    return ctx.db


@tool(
    name="general_info_search",
    description="检索政策/规则/操作手册文档（RAG 向量检索），返回相关知识库原文",
)
def general_info_search(ctx: ToolContext) -> str:
    """RAG 检索：返回知识库原文，无匹配时诚实回复（不编造）。"""
    db = _require_db(ctx)
    query = str(ctx.params.get("query", "")).strip()
    if not query:
        return "请提供要咨询的问题"
    k = ctx.params.get("k", 3)
    try:
        k = int(k)
    except (TypeError, ValueError):
        k = 3
    docs = search_rag(db, query, k=max(1, k))
    if not docs:
        return "未检索到相关政策文档。为避免编造，建议转人工坐席为您核实。"
    return "\n---\n".join(f"[{d.category}] {d.title}\n{d.content}" for d in docs)


@tool(
    name="plan_lookup",
    description="查询套餐介绍与对比（结构化数据）：按套餐名返回资费/流量/通话/简介",
)
def plan_lookup(ctx: ToolContext) -> str:
    """套餐介绍与对比（验收标准2）：params.names 支持多套餐对比。"""
    db = _require_db(ctx)
    raw = ctx.params.get("names", ctx.params.get("name"))
    if raw is None:
        return "请提供套餐名称（params.names）"
    names = raw if isinstance(raw, list) else [raw]
    names = [str(n).strip() for n in names if str(n).strip()]
    if not names:
        return "请提供套餐名称（params.names）"
    plans = query_plans(db, names=names)
    if not plans:
        return "未找到相关套餐，请核对套餐名称。"
    lines = [
        f"[{p.name}] 月费 {p.price:g} 元，流量 {p.data_allowance}，"
        f"通话 {p.call_minutes}；{p.description}"
        for p in plans
    ]
    if len(plans) > 1:
        prices = "、".join(f"{p.name} {p.price:g} 元/月" for p in plans)
        lines.append(f"对比：{prices}")
    return "\n".join(lines)


@tool(
    name="coverage_lookup",
    description="查询网络覆盖情况（结构化数据）：按区域名返回 4G/5G 覆盖等级",
)
def coverage_lookup(ctx: ToolContext) -> str:
    """网络覆盖查询（验收标准2）：params.area 区域名。"""
    db = _require_db(ctx)
    area = str(ctx.params.get("area", "")).strip()
    if not area:
        return "请提供要查询的区域（params.area）"
    rows = query_coverage(db, area=area)
    if not rows:
        return f"未查询到 {area} 的覆盖信息，请核对区域名称。"
    return "\n".join(f"[{r.area}] {r.network_type} 覆盖等级：{r.level}" for r in rows)


@tool(
    name="hall_lookup",
    description="查询营业厅地址（结构化数据）：按区域返回营业厅名称/地址/营业时间",
)
def hall_lookup(ctx: ToolContext) -> str:
    """营业厅地址查询（验收标准2）：params.district 行政区。"""
    db = _require_db(ctx)
    district = str(ctx.params.get("district", "")).strip()
    if not district:
        return "请提供要查询的区域（params.district）"
    halls = query_halls(db, district=district)
    if not halls:
        return f"未查询到 {district} 的营业厅，请核对区域名称。"
    return "\n".join(f"[{h.name}] {h.district} {h.address}（{h.business_hours}）" for h in halls)


#: 本模块全部工具（供 ToolRegistry 批量注册）
GENERAL_INFO_TOOLS = [general_info_search, plan_lookup, coverage_lookup, hall_lookup]


def register_general_info_tools(registry: ToolRegistry) -> None:
    """将通用咨询 tools 注册进 ToolRegistry（B5/B6/#24 组合时统一调用）。"""
    for fn in GENERAL_INFO_TOOLS:
        registry.register(fn)
