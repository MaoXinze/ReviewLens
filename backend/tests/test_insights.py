"""M7 体验洞察看板测试。

- 看板聚合解析：mock get_es().search 返回构造的聚合响应，验证
  情感分布、属性差评率、环比、趋势粒度、SKU 对比、证据下钻。
- 依赖的 model_service.get_current_model 与 review_task_service.summary
  以 async fake 注入，不连接真实 PG/ES。
"""
from types import SimpleNamespace

import pytest

from app.services import insight_service


class _FakeES:
    """按调用顺序返回预设搜索响应；耗尽后返回空结果。"""

    def __init__(self, responses: list | None = None):
        self._responses = list(responses or [])
        self._index = 0

    async def search(self, index=None, body=None, **kwargs):  # noqa: ARG002
        if self._index < len(self._responses):
            resp = self._responses[self._index]
            self._index += 1
            return resp
        return {"hits": {"total": {"value": 0}}, "aggregations": {}}

    def requests(self) -> int:
        return self._index


@pytest.fixture
def fake_model(monkeypatch):
    current = SimpleNamespace(model_version="tfidf-lr-v3")

    async def _get_current_model(db):  # noqa: ARG001
        return current

    monkeypatch.setattr(
        insight_service.model_service, "get_current_model", _get_current_model
    )


@pytest.fixture
def fake_summary(monkeypatch):
    summary = {
        "dataset_version": "ds-x",
        "total": 50,
        "done": 20,
        "pending": 30,
        "approved": 10,
        "verified": 8,
        "rejected": 2,
        "completion_rate": 0.4,
        "agreement_rate": 0.9,
    }

    async def _summary(db, **kwargs):  # noqa: ARG001
        return summary

    monkeypatch.setattr(
        insight_service.review_task_service, "summary", _summary
    )


def _patch_es(monkeypatch, responses):
    fake = _FakeES(responses)
    monkeypatch.setattr(insight_service, "get_es", lambda: fake)
    return fake


# ---------- overview ----------


async def test_overview_aggregates(monkeypatch, fake_model, fake_summary):
    resp = {
        "hits": {"total": {"value": 100}},
        "aggregations": {
            "sentiments": {
                "buckets": [
                    {"key": "positive", "doc_count": 60},
                    {"key": "neutral", "doc_count": 10},
                    {"key": "negative", "doc_count": 30},
                ]
            },
            "top_aspects": {
                "aspect_names": {
                    "buckets": [
                        {
                            "key": "包装",
                            "doc_count": 10,
                            "sentiments": {
                                "buckets": [{"key": "negative", "doc_count": 3}]
                            },
                        },
                        {
                            "key": "电池续航",
                            "doc_count": 25,
                            "sentiments": {
                                "buckets": [
                                    {"key": "negative", "doc_count": 20},
                                    {"key": "positive", "doc_count": 5},
                                ]
                            },
                        },
                    ]
                }
            },
        },
    }
    _patch_es(monkeypatch, [resp])

    result = await insight_service.get_overview(None, "ds-x")

    assert result.dataset_version == "ds-x"
    assert result.model_version == "tfidf-lr-v3"
    assert result.total_reviews == 100
    dist = {(b.overall_sentiment): b for b in result.sentiment_distribution}
    assert dist["negative"].doc_count == 30
    assert abs(dist["positive"].ratio - 0.6) < 0.001
    # top 负向属性：按 negative 数降序，电池续航(20) 在包装(3) 前
    assert result.top_negative_aspects[0].aspect == "电池续航"
    assert result.top_negative_aspects[0].negative == 20
    assert result.review_progress.total == 50
    assert result.review_progress.completion_rate == 0.4


# ---------- aspect-ranking（环比） ----------


async def test_aspect_ranking_prev_change(monkeypatch, fake_model):
    cur = {
        "hits": {"total": {"value": 30}},
        "aggregations": {
            "aspects": {
                "aspect_names": {
                    "buckets": [
                        {
                            "key": "A",
                            "doc_count": 20,
                            "sentiments": {
                                "buckets": [{"key": "negative", "doc_count": 12}]
                            },
                        },
                        {
                            "key": "B",
                            "doc_count": 10,
                            "sentiments": {
                                "buckets": [{"key": "negative", "doc_count": 2}]
                            },
                        },
                    ]
                }
            }
        },
    }
    prev = {
        "hits": {"total": {"value": 30}},
        "aggregations": {
            "aspects": {
                "aspect_names": {
                    "buckets": [
                        {
                            "key": "A",
                            "doc_count": 20,
                            "sentiments": {
                                "buckets": [{"key": "negative", "doc_count": 6}]
                            },
                        },
                        {
                            "key": "B",
                            "doc_count": 10,
                            "sentiments": {
                                "buckets": [{"key": "negative", "doc_count": 1}]
                            },
                        },
                    ]
                }
            }
        },
    }
    fake = _patch_es(monkeypatch, [cur, prev])

    result = await insight_service.get_aspect_ranking(
        None, "ds-x", product_id="B08XYZ", period="2025-08"
    )

    assert fake.requests() == 2  # 当前 + 上一同等窗口两次聚合
    assert result.dataset_version == "ds-x"
    assert result.model_version == "tfidf-lr-v3"
    assert result.filter_conditions["period"] == "2025-08"
    # 排序：差评率降序 A(0.6) > B(0.2)
    assert result.ranking[0].aspect == "A"
    assert result.ranking[0].negative_rate == 0.6  # 12/20
    assert result.ranking[0].prev_rate == 0.3  # 6/20
    assert result.ranking[0].change == 0.3  # 0.6 - 0.3
    assert result.ranking[1].change == 0.1  # 0.2 - 0.1


async def test_aspect_ranking_invalid_period(monkeypatch, fake_model):
    _patch_es(monkeypatch, [])
    with pytest.raises(ValueError):
        await insight_service.get_aspect_ranking(
            None, "ds-x", product_id="B08XYZ", period="2025-13"
        )


async def test_aspect_ranking_no_period_single_query(monkeypatch, fake_model):
    resp = {
        "hits": {"total": {"value": 10}},
        "aggregations": {
            "aspects": {
                "aspect_names": {
                    "buckets": [
                        {
                            "key": "A",
                            "doc_count": 10,
                            "sentiments": {
                                "buckets": [{"key": "negative", "doc_count": 4}]
                            },
                        }
                    ]
                }
            }
        },
    }
    fake = _patch_es(monkeypatch, [resp])
    result = await insight_service.get_aspect_ranking(None, "ds-x")
    assert fake.requests() == 1
    assert result.ranking[0].negative_rate == 0.4
    # 无 period 时无上月窗口可比：环比应为 null（前端显示 —），不能用 0 冒充基线
    assert result.ranking[0].prev_rate is None
    assert result.ranking[0].change is None


# ---------- trends（周/月） ----------


async def test_trends_month_with_aspect(monkeypatch, fake_model):
    resp = {
        "hits": {"total": {"value": 0}},
        "aggregations": {
            "dates": {
                "buckets": [
                    {
                        "key_as_string": "2025-08-01",
                        "doc_count": 100,
                        "matched": {
                            "spec": {
                                "doc_count": 10,
                                "neg": {"doc_count": 4},
                            }
                        },
                    },
                    {
                        "key_as_string": "2025-09-01",
                        "doc_count": 80,
                        "matched": {
                            "spec": {"doc_count": 8, "neg": {"doc_count": 2}}
                        },
                    },
                ]
            }
        },
    }
    fake = _patch_es(monkeypatch, [resp])
    result = await insight_service.get_trends(
        None, "ds-x", granularity="month", aspect="电池续航"
    )

    assert fake.requests() == 1
    assert result.granularity == "month"
    first = result.items[0]
    assert first.bucket == "2025-08-01"
    assert first.total == 10
    assert first.negative == 4
    assert first.negative_rate == 0.4
    assert result.model_version == "tfidf-lr-v3"


async def test_trends_week_no_aspect(monkeypatch, fake_model):
    resp = {
        "hits": {"total": {"value": 0}},
        "aggregations": {
            "dates": {
                "buckets": [
                    {
                        "key_as_string": "2025-08-01",
                        "doc_count": 50,
                        "neg": {"doc_count": 10},
                    }
                ]
            }
        },
    }
    _patch_es(monkeypatch, [resp])
    result = await insight_service.get_trends(None, "ds-x", granularity="week")

    assert result.granularity == "week"
    assert result.items[0].negative_rate == 0.2


# ---------- SKU 对比 ----------


async def test_sku_comparison(monkeypatch, fake_model):
    resp = {
        "hits": {"total": {"value": 0}},
        "aggregations": {
            "sku_buckets": {
                "buckets": [
                    {
                        "key": "B001",
                        "doc_count": 20,
                        "negative": {"doc_count": 8},
                        "top_aspects": {
                            "aspect_names": {
                                "buckets": [
                                    {
                                        "key": "电池续航",
                                        "doc_count": 12,
                                        "sentiments": {
                                            "buckets": [
                                                {"key": "negative", "doc_count": 5}
                                            ]
                                        },
                                    }
                                ]
                            }
                        },
                    },
                    {
                        "key": "B002",
                        "doc_count": 10,
                        "negative": {"doc_count": 2},
                        "top_aspects": {"aspect_names": {"buckets": []}},
                    },
                ]
            }
        },
    }
    fake = _patch_es(monkeypatch, [resp])
    result = await insight_service.get_sku_comparison(None, "ds-x", ["B001", "B002"])

    assert fake.requests() == 1
    assert len(result.skus) == 2
    b1 = result.skus[0]
    assert b1.product_id == "B001"
    assert b1.negative_rate == 0.4  # 8/20
    assert b1.top_aspects[0].aspect == "电池续航"
    b2 = next(s for s in result.skus if s.product_id == "B002")
    assert b2.negative == 2


async def test_sku_comparison_requires_skus(monkeypatch, fake_model):
    _patch_es(monkeypatch, [])
    with pytest.raises(ValueError):
        await insight_service.get_sku_comparison(None, "ds-x", [])


# ---------- 证据下钻 + 与排行一致性 ----------


async def test_evidence_drilldown(monkeypatch):
    resp = {
        "hits": {
            "total": {"value": 3},
            "hits": [
                {
                    "_source": {
                        "review_id": "R1",
                        "product_id": "B08XYZ",
                        "review_title": "续航太差",
                        "review_text": "用了三天就没电",
                        "rating": 1,
                        "reviewed_at": "2025-08-10T00:00:00Z",
                        "overall_sentiment": "negative",
                        "aspects": [
                            {
                                "aspect": "电池续航",
                                "sentiment": "negative",
                                "confidence": 0.85,
                            }
                        ],
                    }
                }
            ],
        }
    }
    _patch_es(monkeypatch, [resp])

    result = await insight_service.get_evidence(
        "ds-x", page=1, page_size=20, aspect="电池续航", sentiment="negative"
    )

    assert result.total == 3
    item = result.items[0]
    assert item.review_id == "R1"
    assert item.review_text == "用了三天就没电"
    assert item.overall_sentiment == "negative"
    assert item.aspects[0]["aspect"] == "电池续航"


async def test_evidence_total_matches_ranking_negative(monkeypatch, fake_model):
    """验收标准 1：排行 negative 数 = 同条件下钻评论数之和。"""
    ranking_resp = {
        "hits": {"total": {"value": 20}},
        "aggregations": {
            "aspects": {
                "aspect_names": {
                    "buckets": [
                        {
                            "key": "电池续航",
                            "doc_count": 89,
                            "sentiments": {
                                "buckets": [{"key": "negative", "doc_count": 20}]
                            },
                        }
                    ]
                }
            }
        },
    }
    evidence_resp = {
        "hits": {"total": {"value": 20}, "hits": []},
    }
    # get_aspect_ranking(带 period) 会发两次聚合：当前窗口 + 上一窗口
    prev_resp = {
        "hits": {"total": {"value": 20}},
        "aggregations": {
            "aspects": {"aspect_names": {"buckets": []}},
        },
    }
    _patch_es(monkeypatch, [ranking_resp, prev_resp, evidence_resp])

    ranking = await insight_service.get_aspect_ranking(
        None, "ds-x", product_id="B08XYZ", period="2025-08"
    )
    avg = ranking.ranking[0]
    assert avg.negative == 20

    evidence = await insight_service.get_evidence(
        "ds-x",
        page=1,
        page_size=20,
        product_id="B08XYZ",
        aspect="电池续航",
        sentiment="negative",
        period="2025-08",
    )
    # 相同过滤条件下，下钻评论总数等于排行 negative 数
    assert evidence.total == avg.negative == 20
