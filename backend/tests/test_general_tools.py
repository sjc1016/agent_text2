"""B4 通用咨询 tool 测试（验收标准1+2，tool 调用 seam）。

PRD 依据：
  - 验收标准1：通用咨询 tool 检索 RAG 向量库返回相关政策/规则/手册内容，不编造
    （PRD 依据：`PRD 实现决策 › 知识来源`；`PRD 测试决策 › tool 调用 seam`；`用户故事 US-1`）
  - 验收标准2：套餐介绍与对比、网络覆盖、营业厅地址查询返回结构化数据
    （PRD 依据：`PRD 实现决策 › 知识来源`；`用户故事 US-1`）

行为 SSOT：issue 验收标准 + PRD「测试决策 › tool 调用 seam」
（LangChain tools 作为纯函数测试，与 LLM 调用解耦）。
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.agent.general_tools import register_general_info_tools
from app.agent.tools import ToolContext, ToolRegistry
from app.general.service import (
    CREATE_VEC_TABLE_SQL,
    index_knowledge_document,
    search_rag,
)


@pytest.fixture
def vec_db(db):
    """建 vec0 虚拟表。

    sqlite-vec 的虚拟表不经 Base.metadata（create_all 不覆盖），测试内显式创建；
    生产环境由 Alembic 迁移 0006 创建（验收标准4）。
    """
    db.execute(sa.text(CREATE_VEC_TABLE_SQL))
    db.commit()
    return db


class TestRagSearchTool:
    """验收标准1：RAG 检索返回知识库原文，不编造。"""

    def _seed(self, db) -> None:
        index_knowledge_document(
            db,
            category="policy",
            title="合约期内销户政策",
            content="合约期内原则上不允许销户；如需销户须支付违约金，详见合约条款。",
        )
        index_knowledge_document(
            db,
            category="manual",
            title="5G 套餐变更操作手册",
            content="用户可在中国电信 APP 或营业厅办理 5G 套餐变更。",
        )

    def test_search_returns_seeded_document_content(self, vec_db):
        """RAG 检索返回知识库原文（政策/规则/手册），不返回无关文档（不编造）。"""
        self._seed(vec_db)

        registry = ToolRegistry()
        register_general_info_tools(registry)

        result = registry.invoke(
            "general_info_search",
            ToolContext(db=vec_db, params={"query": "合约期内能否销户"}),
        )
        assert "合约期内销户政策" in result
        assert "违约金" in result
        # 无关文档不应被检索（不编造：只返回知识库中存在的相关内容）
        assert "5G 套餐变更操作手册" not in result

    def test_search_service_orders_relevant_doc_first(self, vec_db):
        """服务层检索：相关文档排第一，且返回内容为知识库原文。"""
        self._seed(vec_db)

        docs = search_rag(vec_db, "合约期内能否销户")
        assert docs, "应检索到相关知识文档"
        assert docs[0].title == "合约期内销户政策"
        assert "违约金" in docs[0].content

    def test_search_no_match_does_not_fabricate(self, vec_db):
        """无匹配：诚实回复未检索到，不编造答案。"""
        self._seed(vec_db)

        registry = ToolRegistry()
        register_general_info_tools(registry)

        result = registry.invoke(
            "general_info_search",
            ToolContext(db=vec_db, params={"query": "今天天气怎么样"}),
        )
        assert "未检索到" in result
        assert "5G 套餐变更操作手册" not in result


# ---------------------------------------------------------------------------
# 循环3：结构化查询 tool（验收标准2 — 套餐介绍与对比 / 网络覆盖 / 营业厅地址）
# PRD 依据：`PRD 实现决策 › 知识来源`（结构化数据）；`用户故事 US-1`
# ---------------------------------------------------------------------------


class TestPlanLookupTool:
    """套餐介绍与对比（结构化数据）：按名称返回资费/流量/通话/简介，支持多套餐对比。"""

    def test_plan_lookup_returns_plan_details(self, db):
        """单套餐查询：返回月费/流量/通话/简介原文。"""
        from app.models.general import Plan

        db.add(
            Plan(
                name="畅享5G套餐",
                price=99.0,
                data_allowance="30GB",
                call_minutes="500分钟",
                description="面向家庭用户的 5G 基础套餐",
            )
        )
        db.commit()

        registry = ToolRegistry()
        register_general_info_tools(registry)
        result = registry.invoke(
            "plan_lookup",
            ToolContext(db=db, params={"name": "畅享5G套餐"}),
        )
        assert "畅享5G套餐" in result
        assert "99" in result
        assert "30GB" in result
        assert "500分钟" in result

    def test_plan_lookup_compares_multiple_plans(self, db):
        """多套餐对比：params.names 传入多个套餐名，输出含对比行。"""
        from app.models.general import Plan

        db.add_all(
            [
                Plan(name="畅享5G套餐", price=99.0, data_allowance="30GB"),
                Plan(name="尊享5G套餐", price=199.0, data_allowance="80GB"),
            ]
        )
        db.commit()

        registry = ToolRegistry()
        register_general_info_tools(registry)
        result = registry.invoke(
            "plan_lookup",
            ToolContext(db=db, params={"names": ["畅享5G套餐", "尊享5G套餐"]}),
        )
        assert "畅享5G套餐" in result
        assert "尊享5G套餐" in result
        assert "对比" in result

    def test_plan_lookup_no_match_replies_honestly(self, db):
        """无匹配：诚实回复未找到，不编造套餐信息。"""
        registry = ToolRegistry()
        register_general_info_tools(registry)
        result = registry.invoke(
            "plan_lookup",
            ToolContext(db=db, params={"name": "不存在的套餐"}),
        )
        assert "未找到相关套餐" in result


class TestCoverageLookupTool:
    """网络覆盖查询（结构化数据）：按区域返回 4G/5G 覆盖等级。"""

    def test_coverage_lookup_returns_levels(self, db):
        from app.models.general import CoverageArea

        db.add_all(
            [
                CoverageArea(area="天府新区", network_type="5G", level="full"),
                CoverageArea(area="天府新区", network_type="4G", level="full"),
            ]
        )
        db.commit()

        registry = ToolRegistry()
        register_general_info_tools(registry)
        result = registry.invoke(
            "coverage_lookup",
            ToolContext(db=db, params={"area": "天府新区"}),
        )
        assert "天府新区" in result
        assert "5G" in result
        assert "覆盖等级" in result

    def test_coverage_lookup_no_match_replies_honestly(self, db):
        """无匹配：诚实回复未查询到，不编造覆盖信息。"""
        registry = ToolRegistry()
        register_general_info_tools(registry)
        result = registry.invoke(
            "coverage_lookup",
            ToolContext(db=db, params={"area": "不存在的区"}),
        )
        assert "未查询到" in result


class TestHallLookupTool:
    """营业厅地址查询（结构化数据）：按行政区返回名称/地址/营业时间。"""

    def test_hall_lookup_returns_hall_details(self, db):
        from app.models.general import BusinessHall

        db.add(
            BusinessHall(
                name="高新营业厅",
                district="高新区",
                address="天府大道北段 1700 号",
                business_hours="9:00-17:00",
            )
        )
        db.commit()

        registry = ToolRegistry()
        register_general_info_tools(registry)
        result = registry.invoke(
            "hall_lookup",
            ToolContext(db=db, params={"district": "高新区"}),
        )
        assert "高新营业厅" in result
        assert "天府大道北段" in result
        assert "9:00-17:00" in result

    def test_hall_lookup_no_match_replies_honestly(self, db):
        """无匹配：诚实回复未查询到，不编造营业厅信息。"""
        registry = ToolRegistry()
        register_general_info_tools(registry)
        result = registry.invoke(
            "hall_lookup",
            ToolContext(db=db, params={"district": "不存在的区"}),
        )
        assert "未查询到" in result
