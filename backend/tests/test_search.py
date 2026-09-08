"""M3 评论搜索引擎测试。

- 查询构建 / 聚合解析：纯函数单测（无需 ES）
- 搜索 / 聚合集成：连接真实 ES（不可用时自动跳过），使用独立测试索引 reviews_test_m3
"""
import urllib.request
from datetime import date

import pytest
from elasticsearch import AsyncElasticsearch

from app.core.config import settings
from app.core.es import bulk_index_reviews, ensure_reviews_index, get_es
from app.schemas.search import (
    AggregateFilters,
    AggregateRequest,
    SearchFilters,
    SearchRequest,
)
from app.services import search_service

ES_TEST_INDEX = "reviews_test_m3"


def es_available() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:9200", timeout=1):
            return True
    except Exception:
        return False


# ---------- 查询构建（纯函数） ----------

def test_search_query_multi_match_ik():
    req = SearchRequest(query="续航 差")
    body = search_service.build_search_query(req)
    must = body["query"]["bool"]["must"]
    assert must[0]["multi_match"]["query"] == "续航 差"
    assert must[0]["multi_match"]["analyzer"] == "ik_smart"
    assert must[0]["multi_match"]["fields"] == ["review_title^2", "review_text"]
    assert body["from"] == 0
    assert body["size"] == 20


def test_search_query_filters_combined():
    req = SearchRequest(
        filters=SearchFilters(
            dataset_version="ds-x",
            product_id="B08XYZ",
            rating_min=1,
            rating_max=2,
            date_from=date(2025, 8, 1),
            language="zh",
            overall_sentiment="negative",
            aspect="电池续航",
        )
    )
    filters = search_service.build_search_query(req)["query"]["bool"]["filter"]
    assert {"term": {"dataset_version": "ds-x"}} in filters
    assert {"term": {"product_id": "B08XYZ"}} in filters
    assert {"range": {"rating": {"gte": 1, "lte": 2}}} in filters
    assert {"range": {"reviewed_at": {"gte": "2025-08-01"}}} in filters
    assert {"term": {"language": "zh"}} in filters
    assert {"term": {"overall_sentiment": "negative"}} in filters
    assert {
        "nested": {
            "path": "aspects",
            "query": {"term": {"aspects.aspect": "电池续航"}},
        }
    } in filters


def test_search_sort_and_pagination():
    body = search_service.build_search_query(
        SearchRequest(sort_by="date", page=2, page_size=50)
    )
    assert body["sort"] == [{"reviewed_at": {"order": "desc"}}]
    assert body["from"] == 50
    assert body["size"] == 50


def test_search_highlight():
    body = search_service.build_search_query(SearchRequest(query="续航"))
    hl = body["highlight"]
    assert hl["pre_tags"] == ["<em>"]
    assert hl["post_tags"] == ["</em>"]
    assert "review_title" in hl["fields"]
    assert "review_text" in hl["fields"]


# ---------- 聚合查询构建（纯函数） ----------

def test_aggregate_aspect_nested():
    body = search_service.build_aggregation_query(AggregateRequest(group_by="aspect"))
    assert body["size"] == 0
    aspects = body["aggs"]["aspects"]
    assert aspects["nested"]["path"] == "aspects"
    assert "aspect_names" in aspects["aggs"]


def test_aggregate_rating_date_sentiment():
    rating = search_service.build_aggregation_query(AggregateRequest(group_by="rating"))
    assert "ratings" in rating["aggs"]

    dates = search_service.build_aggregation_query(
        AggregateRequest(group_by="date", date_histogram="week")
    )
    assert dates["aggs"]["dates"]["date_histogram"]["calendar_interval"] == "week"

    sentiment = search_service.build_aggregation_query(
        AggregateRequest(group_by="sentiment")
    )
    assert "sentiments" in sentiment["aggs"]


def test_aggregate_filters_include_dataset_version():
    body = search_service.build_aggregation_query(
        AggregateRequest(
            dataset_version="ds-x",
            filters=AggregateFilters(product_id="B08XYZ", rating_min=3),
        )
    )
    filters = body["query"]["bool"]["filter"]
    assert {"term": {"dataset_version": "ds-x"}} in filters
    assert {"term": {"product_id": "B08XYZ"}} in filters
    assert {"range": {"rating": {"gte": 3}}} in filters


# ---------- 聚合结果解析（纯函数） ----------

def test_parse_aspect_buckets():
    aggs = {
        "aspects": {
            "aspect_names": {
                "buckets": [
                    {
                        "key": "电池续航",
                        "doc_count": 89,
                        "sentiments": {
                            "buckets": [
                                {"key": "negative", "doc_count": 34},
                                {"key": "positive", "doc_count": 55},
                            ]
                        },
                        "avg_confidence": {"value": 0.82},
                    },
                ]
            }
        }
    }
    buckets = search_service._parse_buckets("aspect", aggs)
    assert buckets[0].key == "电池续航"
    assert buckets[0].doc_count == 89
    assert buckets[0].negative_count == 34
    assert buckets[0].positive_count == 55
    assert abs(buckets[0].negative_rate - 0.382) < 0.001
    assert buckets[0].avg_confidence == 0.82


def test_parse_rating_and_sentiment_buckets():
    rating = search_service._parse_buckets(
        "rating",
        {
            "ratings": {
                "buckets": [
                    {"key": 1, "doc_count": 10, "negative": {"doc_count": 8}},
                ]
            }
        },
    )
    assert rating[0].key == "1"
    assert rating[0].negative_count == 8
    assert rating[0].negative_rate == 0.8

    sentiment = search_service._parse_buckets(
        "sentiment",
        {
            "sentiments": {
                "buckets": [
                    {"key": "negative", "doc_count": 3},
                    {"key": "positive", "doc_count": 7},
                ]
            }
        },
    )
    assert sentiment[0].negative_rate == 1.0
    assert sentiment[1].negative_rate == 0.0


# ---------- 集成测试（需 ES 运行，否则自动跳过） ----------

@pytest.mark.skipif(not es_available(), reason="ES 未运行，跳过集成测试")
class TestESIntegration:
    @pytest.fixture(autouse=True)
    async def _es_test_index(self):
        """每个测试使用独立 ES 客户端与测试索引，避免跨事件循环复用全局客户端。"""
        from app.core import es as es_mod

        old_index = settings.reviews_index
        settings.reviews_index = ES_TEST_INDEX
        client = AsyncElasticsearch("http://localhost:9200")
        es_mod._client = client  # 让 get_es() 返回本测试专用客户端
        try:
            await client.indices.delete(index=ES_TEST_INDEX, ignore_unavailable=True)
            await ensure_reviews_index()
            yield
        finally:
            await client.indices.delete(index=ES_TEST_INDEX, ignore_unavailable=True)
            await client.close()
            es_mod._client = None
            settings.reviews_index = old_index

    async def _seed(self):
        docs = [
            {
                "dataset_version": "ds-test",
                "review_id": "R1",
                "product_id": "B001",
                "product_group_id": "G1",
                "review_title": "电池续航很好",
                "review_text": "续航持久 充电也快",
                "rating": 5,
                "reviewed_at": "2025-08-10T00:00:00Z",
                "language": "zh",
                "helpful_votes": 3,
                "verified_purchase": True,
                "overall_sentiment": "positive",
                "aspects": [
                    {"aspect": "电池续航", "sentiment": "positive", "confidence": 0.9}
                ],
                "model_version": "test",
            },
            {
                "dataset_version": "ds-test",
                "review_id": "R2",
                "product_id": "B001",
                "product_group_id": "G1",
                "review_title": "续航太差",
                "review_text": "用了三天就没电 续航非常差",
                "rating": 1,
                "reviewed_at": "2025-08-12T00:00:00Z",
                "language": "zh",
                "helpful_votes": 5,
                "verified_purchase": True,
                "overall_sentiment": "negative",
                "aspects": [
                    {"aspect": "电池续航", "sentiment": "negative", "confidence": 0.85}
                ],
                "model_version": "test",
            },
            {
                "dataset_version": "ds-test",
                "review_id": "R3",
                "product_id": "B002",
                "product_group_id": "G2",
                "review_title": "一般般",
                "review_text": "没什么特别的感觉",
                "rating": 3,
                "reviewed_at": "2025-08-20T00:00:00Z",
                "language": "zh",
                "helpful_votes": 0,
                "verified_purchase": False,
                "overall_sentiment": "neutral",
                "aspects": [],
                "model_version": "test",
            },
        ]
        await bulk_index_reviews(docs, "ds-test")
        es = get_es()
        await es.indices.refresh(index=ES_TEST_INDEX)

    async def test_service_search(self):
        await self._seed()
        result = await search_service.search_reviews(
            SearchRequest(query="续航", page_size=10)
        )
        assert result.total >= 2
        assert all(h.review_id in {"R1", "R2"} for h in result.items)
        assert any("续航" in "".join(h.highlight) for h in result.items)

    async def test_service_search_with_filters(self):
        await self._seed()
        result = await search_service.search_reviews(
            SearchRequest(
                query="续航",
                filters=SearchFilters(dataset_version="ds-test", rating_min=4),
            )
        )
        assert result.total == 1
        assert result.items[0].review_id == "R1"

    async def test_service_aggregate_aspect(self):
        await self._seed()
        result = await search_service.aggregate_reviews(
            AggregateRequest(dataset_version="ds-test", group_by="aspect")
        )
        assert result.total_docs == 3
        bucket = next(b for b in result.buckets if b.key == "电池续航")
        assert bucket.doc_count == 2
        assert bucket.negative_count == 1
        assert bucket.negative_rate == 0.5

    async def test_api_search_endpoint(self, client):
        await self._seed()
        await client.post(
            "/api/auth/register",
            json={
                "email": "m3@example.com",
                "password": "Passw0rd!",
                "full_name": "M3",
            },
        )
        login = await client.post(
            "/api/auth/login", json={"email": "m3@example.com", "password": "Passw0rd!"}
        )
        token = login.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/reviews/search", json={"query": "续航"}, headers=headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["total"] >= 2

        agg = await client.post(
            "/api/v1/reviews/aggregate",
            json={"dataset_version": "ds-test", "group_by": "aspect"},
            headers=headers,
        )
        assert agg.status_code == 200
        assert agg.json()["data"]["total_docs"] == 3

    async def test_api_search_requires_auth(self, client):
        resp = await client.post("/api/v1/reviews/search", json={"query": "续航"})
        assert resp.status_code == 401
