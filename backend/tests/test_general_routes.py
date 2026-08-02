"""B4 REST `/general-info/*` 免认证测试（验收标准3）。

PRD 依据：
  - 验收标准3：Visitor 无需认证即可调用 /general-info/*
    （PRD 依据：`CONTEXT.md › 业务能力 / 通用咨询类`；`用户故事 US-1`）
  - 测试决策 › HTTP 集成 seam（REST 请求/响应形状、状态码、鉴权边界）
  - 实现决策 › API 契约（/general-info/* 通用咨询）

行为：未携带任何凭据（匿名）即可访问四个端点 → 200；返回结构化 JSON；
RAG 无匹配返回空列表（不编造）。
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.general.service import CREATE_VEC_TABLE_SQL, index_knowledge_document


@pytest.fixture
def vec_db(db):
    """建 vec0 虚拟表（与 tool 测试一致；生产由迁移 0006 创建）。"""
    db.execute(sa.text(CREATE_VEC_TABLE_SQL))
    db.commit()
    return db


class TestGeneralInfoAnonymous:
    """Visitor 免认证（验收标准3）：无 Authorization header 亦可访问。"""

    async def test_search_anonymous_returns_docs(self, db_client, db, vec_db):
        """匿名 GET /general-info/search 返回知识库原文（US-1）。"""
        index_knowledge_document(
            db,
            category="policy",
            title="合约期内销户政策",
            content="合约期内原则上不允许销户；如需销户须支付违约金。",
        )

        resp = await db_client.get("/general-info/search", params={"query": "合约期内能否销户"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list) and data
        titles = [item["title"] for item in data]
        assert "合约期内销户政策" in titles

    async def test_search_no_match_returns_empty_list(self, db_client, db, vec_db):
        """无匹配：返回空列表（不编造）。"""
        index_knowledge_document(
            db,
            category="policy",
            title="合约期内销户政策",
            content="合约期内原则上不允许销户。",
        )

        resp = await db_client.get("/general-info/search", params={"query": "今天天气怎么样"})
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_plans_anonymous_returns_structured_data(self, db_client, db):
        """匿名 GET /general-info/plans 返回套餐结构化数据（US-1）。"""
        from app.models.general import Plan

        db.add(
            Plan(
                name="畅享5G套餐",
                price=99.0,
                data_allowance="30GB",
                call_minutes="500分钟",
            )
        )
        db.commit()

        resp = await db_client.get("/general-info/plans", params={"names": ["畅享5G套餐"]})
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["name"] == "畅享5G套餐"
        assert data[0]["price"] == 99.0
        assert data[0]["data_allowance"] == "30GB"

    async def test_coverage_anonymous_returns_structured_data(self, db_client, db):
        """匿名 GET /general-info/coverage 返回覆盖结构化数据（US-1）。"""
        from app.models.general import CoverageArea

        db.add(CoverageArea(area="天府新区", network_type="5G", level="full"))
        db.commit()

        resp = await db_client.get("/general-info/coverage", params={"area": "天府新区"})
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["area"] == "天府新区"
        assert data[0]["network_type"] == "5G"

    async def test_halls_anonymous_returns_structured_data(self, db_client, db):
        """匿名 GET /general-info/halls 返回营业厅结构化数据（US-1）。"""
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

        resp = await db_client.get("/general-info/halls", params={"district": "高新区"})
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["name"] == "高新营业厅"
        assert data[0]["address"] == "天府大道北段 1700 号"
