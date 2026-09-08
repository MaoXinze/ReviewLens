"""M7 体验洞察看板服务：基于 ES 聚合看板指标与证据下钻。

不新建数据库表，全部基于 Elasticsearch 索引 settings.reviews_index
（含 M4/M6 写入的 overall_sentiment / aspects / model_version）。
审核进度复用 M5 的 review_task_service.summary，当前生产模型版本
复用 M6 的 model_service.get_current_model。
"""
from datetime import UTC, datetime, timedelta

from elasticsearch.exceptions import TransportError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.es import get_es
from app.schemas.insight import (
    AspectRankingResponse,
    AspectRate,
    EvidenceItem,
    EvidenceResponse,
    InsightOverView,
    ReviewProgress,
    SentimentBucket,
    SkuComparisonResponse,
    SkuStat,
    TrendPoint,
    TrendsResponse,
)
from app.services import model_service, review_task_service

_NEGATIVE = "negative"
_ASPECT_TOP_N = 50


class InsightUnavailable(Exception):
    """ES 不可用或查询失败，路由层转为 503。"""


async def _search(body: dict) -> dict:
    """执行 ES 搜索；TransportError 统一转为 InsightUnavailable。"""
    try:
        return await get_es().search(index=settings.reviews_index, body=body)
    except TransportError as exc:
        raise InsightUnavailable(f"ES 看板查询失败: {exc}") from exc


def _base_filters(
    dataset_version: str, product_id: str | None = None
) -> list[dict]:
    """基础过滤：数据集 + 可选商品。"""
    filters: list[dict] = [{"term": {"dataset_version": dataset_version}}]
    if product_id:
        filters.append({"term": {"product_id": product_id}})
    return filters


def _period_range(period: str) -> dict | None:
    """校验并解析月窗口（供属性排行/证据使用）；返回 reviewed_at range filter。

    period 形如 '2025-08'。
    """
    try:
        year, month = (int(x) for x in period.split("-"))
        if not (1 <= month <= 12):
            return None
    except (ValueError, AttributeError):
        return None
    start = datetime(year, month, 1, tzinfo=UTC)
    nxt = datetime(year + 1, 1, 1, tzinfo=UTC) if month == 12 else datetime(
        year, month + 1, 1, tzinfo=UTC
    )
    return {
        "range": {"reviewed_at": {"gte": start.isoformat(), "lt": nxt.isoformat()}}
    }


def _trend_window(period: str, granularity: str) -> dict | None:
    """校验并解析趋势下钻窗口，返回 reviewed_at range filter；非法返回 None。

    period 形如：
      - granularity=month → '2025'       （该年 12 个月）
      - granularity=week  → '2025-08'    （该月内周）
      - granularity=day   → '2025-08-11' （该日期所在周，7 天）
    """
    try:
        if granularity == "month":
            year = int(period)
            start = datetime(year, 1, 1, tzinfo=UTC)
            nxt = datetime(year + 1, 1, 1, tzinfo=UTC)
        elif granularity == "week":
            year, month = (int(x) for x in period.split("-"))
            if not (1 <= month <= 12):
                return None
            start = datetime(year, month, 1, tzinfo=UTC)
            nxt = datetime(year + 1, 1, 1, tzinfo=UTC) if month == 12 else datetime(
                year, month + 1, 1, tzinfo=UTC
            )
        elif granularity == "day":
            year, month, day = (int(x) for x in period.split("-"))
            d = datetime(year, month, day, tzinfo=UTC)
            # 周从周一开始，取周一 0 点 ~ 周日 24 点
            start = d - timedelta(days=d.weekday())
            nxt = start + timedelta(days=7)
        else:
            return None
    except (ValueError, AttributeError):
        return None
    return {
        "range": {"reviewed_at": {"gte": start.isoformat(), "lt": nxt.isoformat()}}
    }


def _prev_period_range(period: str) -> dict | None:
    """上一同等月窗口范围（与 _period_range 同月长度）。"""
    try:
        year, month = (int(x) for x in period.split("-"))
        if not (1 <= month <= 12):
            return None
    except (ValueError, AttributeError):
        return None
    if month == 1:
        prev = datetime(year - 1, 12, 1, tzinfo=UTC)
    else:
        prev = datetime(year, month - 1, 1, tzinfo=UTC)
    return {
        "range": {
            "reviewed_at": {
                "gte": prev.isoformat(),
                "lt": _first_of_next(prev).isoformat(),
            }
        }
    }


def _first_of_next(dt: datetime) -> datetime:
    if dt.month == 12:
        return datetime(dt.year + 1, 1, 1, tzinfo=UTC)
    return datetime(dt.year, dt.month + 1, 1, tzinfo=UTC)


# ---------- 聚合构建 ----------


def _aspect_agg_builder(size: int = _ASPECT_TOP_N) -> dict:
    """nested aspects 聚合：按属性分桶并统计情感。"""
    return {
        "nested": {"path": "aspects"},
        "aggs": {
            "aspect_names": {
                "terms": {"field": "aspects.aspect", "size": size},
                "aggs": {
                    "sentiments": {"terms": {"field": "aspects.sentiment"}},
                },
            }
        },
    }


def _aspect_rates_from(agg_bucket: dict) -> list[AspectRate]:
    """把 nested aspects 聚合桶解析为 AspectRate 列表（无环比）。"""
    out: list[AspectRate] = []
    buckets = (
        agg_bucket.get("aspect_names", {}).get("buckets", [])
        if agg_bucket
        else []
    )
    for bucket in buckets:
        counts = {
            s["key"]: s["doc_count"]
            for s in bucket.get("sentiments", {}).get("buckets", [])
        }
        total = bucket["doc_count"]
        negative = counts.get(_NEGATIVE, 0)
        rate = round(negative / total, 4) if total else 0.0
        out.append(
            AspectRate(
                aspect=bucket["key"],
                total=total,
                negative=negative,
                negative_rate=rate,
            )
        )
    return out


async def _current_model_version(db: AsyncSession) -> str | None:
    """当前生产模型版本（无则 None）。"""
    current = await model_service.get_current_model(db)
    return current.model_version if current else None


# ---------- 看板指标 ----------


async def get_overview(
    db: AsyncSession, dataset_version: str, product_id: str | None = None
) -> InsightOverView:
    """总览：评论量 + 情感分布 + 差评属性 top + 审核进度。"""
    filters = _base_filters(dataset_version, product_id)
    body = {
        "size": 0,
        # ES 默认在 10000 条处截断 total，会让情感占比的分母失真（占比>100%）
        "track_total_hits": True,
        "query": {"bool": {"filter": filters}},
        "aggs": {
            "sentiments": {"terms": {"field": "overall_sentiment", "size": 5}},
            "top_aspects": _aspect_agg_builder(),
        },
    }
    resp = await _search(body)
    total = resp["hits"]["total"]["value"]
    aggs = resp.get("aggregations", {})

    sentiment_buckets = aggs.get("sentiments", {}).get("buckets", [])
    distribution = [
        SentimentBucket(
            overall_sentiment=b["key"],
            doc_count=b["doc_count"],
            ratio=round(b["doc_count"] / total, 4) if total else 0.0,
        )
        for b in sentiment_buckets
    ]

    top_aspects = _aspect_rates_from(aggs.get("top_aspects"))
    top_aspects.sort(key=lambda a: a.negative, reverse=True)
    top_negative = top_aspects[:5]

    progress = await review_task_service.summary(
        db, dataset_version=dataset_version
    )
    model_version = await _current_model_version(db)

    return InsightOverView(
        dataset_version=dataset_version,
        model_version=model_version,
        generated_at=datetime.now(UTC),
        total_reviews=total,
        sentiment_distribution=distribution,
        top_negative_aspects=top_negative,
        review_progress=ReviewProgress(**progress),
    )


async def _aspect_rates_for(filters: list[dict]) -> list[AspectRate]:
    """对给定过滤条件做一次 nested 属性差评率聚合。"""
    body = {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {"aspects": _aspect_agg_builder()},
    }
    resp = await _search(body)
    return _aspect_rates_from(resp.get("aggregations", {}).get("aspects"))


async def get_aspect_ranking(
    db: AsyncSession,
    dataset_version: str,
    product_id: str | None = None,
    period: str | None = None,
) -> AspectRankingResponse:
    """属性差评率排行 + 上一同等窗口环比。"""
    base = _base_filters(dataset_version, product_id)
    filter_conditions: dict = {"product_id": product_id}
    if period:
        cur_range = _period_range(period)
        if cur_range is None:
            raise ValueError("period 格式非法，应为 YYYY-MM")
        base.append(cur_range)
        prev_range = _prev_period_range(period)
        filter_conditions["period"] = period
    else:
        cur_range = prev_range = None

    current_rows = await _aspect_rates_for(base)
    prev_rows = []
    if cur_range is not None and prev_range is not None:
        prev_rows = await _aspect_rates_for(
            _base_filters(dataset_version, product_id) + [prev_range]
        )

    prev_by_aspect = {r.aspect: r for r in prev_rows}
    ranking = []
    for row in current_rows:
        prev = prev_by_aspect.get(row.aspect)
        if prev is None:
            # 上月无该属性数据：环比无从计算，置 null（前端显示 —），不能用 0 冒充基线
            row.prev_rate = None
            row.change = None
        else:
            row.prev_rate = prev.negative_rate
            row.change = round(row.negative_rate - prev.negative_rate, 4)
        ranking.append(row)

    ranking.sort(key=lambda a: a.negative_rate, reverse=True)
    return AspectRankingResponse(
        dataset_version=dataset_version,
        model_version=await _current_model_version(db),
        generated_at=datetime.now(UTC),
        filter_conditions=filter_conditions,
        ranking=ranking,
    )


def _trend_body(
    filters: list[dict], granularity: str, aspect: str | None
) -> dict:
    """趋势聚合请求体：date_histogram + 差评计数（可按属性过滤）。"""
    histogram = {
        "date_histogram": {
            "field": "reviewed_at",
            "calendar_interval": granularity,
        }
    }
    if aspect:
        histogram["aggs"] = {
            "matched": {
                "nested": {"path": "aspects"},
                "aggs": {
                    "spec": {
                        "filter": {"term": {"aspects.aspect": aspect}},
                        "aggs": {
                            "neg": {
                                "filter": {
                                    "term": {"aspects.sentiment": _NEGATIVE}
                                }
                            }
                        },
                    }
                },
            }
        }
    else:
        histogram["aggs"] = {
            "neg": {"filter": {"term": {"overall_sentiment": _NEGATIVE}}}
        }
    return {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {"dates": histogram},
    }


async def get_trends(
    db: AsyncSession,
    dataset_version: str,
    product_id: str | None = None,
    aspect: str | None = None,
    granularity: str = "month",
    period: str | None = None,
) -> TrendsResponse:
    """属性差评率趋势时间序列（分层下钻：年→月→周→日）。

    granularity + period 决定展示窗口：
      - month + '2025'       → 该年 12 个月
      - week  + '2025-08'    → 该月内周
      - day   + '2025-08-11' → 该日期所在周 7 天
      - year / 无 period      → 全量按对应粒度聚合（向后兼容）
    """
    filters = _base_filters(dataset_version, product_id)
    window = _trend_window(period, granularity) if period else None
    if window:
        filters.append(window)
    body = _trend_body(filters, granularity, aspect)
    resp = await _search(body)
    items: list[TrendPoint] = []
    for bucket in resp.get("aggregations", {}).get("dates", {}).get("buckets", []):
        if aspect:
            spec = bucket.get("matched", {}).get("spec", {})
            total = spec["doc_count"]
            negative = spec.get("neg", {}).get("doc_count", 0)
        else:
            total = bucket["doc_count"]
            negative = bucket.get("neg", {}).get("doc_count", 0)
        key = bucket.get("key_as_string") or str(bucket["key"])
        items.append(
            TrendPoint(
                bucket=key,
                total=total,
                negative=negative,
                negative_rate=round(negative / total, 4) if total else 0.0,
            )
        )
    return TrendsResponse(
        dataset_version=dataset_version,
        model_version=await _current_model_version(db),
        granularity=granularity,
        period=period,
        items=items,
    )


async def get_sku_comparison(
    db: AsyncSession,
    dataset_version: str,
    skus: list[str],
    aspect: str | None = None,
) -> SkuComparisonResponse:
    """多 SKU 属性对比：差评率 + 各自 top 属性。"""
    if not skus:
        raise ValueError("至少需要 1 个 SKU")
    filters = _base_filters(dataset_version) + [
        {"terms": {"product_id": skus}}
    ]
    if aspect:
        filters.append(
            {
                "nested": {
                    "path": "aspects",
                    "query": {"term": {"aspects.aspect": aspect}},
                }
            }
        )
    body = {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        "aggs": {
            "sku_buckets": {
                "terms": {"field": "product_id", "size": len(skus)},
                "aggs": {
                    "negative": {
                        "filter": {"term": {"overall_sentiment": _NEGATIVE}}
                    },
                    "top_aspects": _aspect_agg_builder(size=5),
                },
            }
        },
    }
    resp = await _search(body)
    raw = {
        b["key"]: b
        for b in resp.get("aggregations", {}).get("sku_buckets", {}).get("buckets", [])
    }
    sku_stats: list[SkuStat] = []
    for sku in skus:
        bucket = raw.get(sku)
        if not bucket:
            continue
        total = bucket["doc_count"]
        negative = bucket.get("negative", {}).get("doc_count", 0)
        top_aspects = _aspect_rates_from(bucket.get("top_aspects"))
        top_aspects.sort(key=lambda a: a.negative, reverse=True)
        sku_stats.append(
            SkuStat(
                product_id=sku,
                total=total,
                negative=negative,
                negative_rate=round(negative / total, 4) if total else 0.0,
                top_aspects=top_aspects[:5],
            )
        )
    return SkuComparisonResponse(
        dataset_version=dataset_version,
        model_version=await _current_model_version(db),
        skus=sku_stats,
    )


# ---------- 证据下钻 ----------


def _evidence_filters(
    dataset_version: str,
    product_id: str | None,
    aspect: str | None,
    sentiment: str | None,
    period: str | None,
) -> list[dict]:
    """证据查询过滤：聚合数字可下钻到同条件的原始评论。"""
    filters = _base_filters(dataset_version, product_id)
    if period:
        rng = _period_range(period)
        if rng is not None:
            filters.append(rng)
    if aspect:
        inner: list[dict] = [{"term": {"aspects.aspect": aspect}}]
        if sentiment:
            inner.append({"term": {"aspects.sentiment": sentiment}})
        filters.append(
            {
                "nested": {
                    "path": "aspects",
                    "query": {"bool": {"must": inner}},
                }
            }
        )
    elif sentiment:
        filters.append({"term": {"overall_sentiment": sentiment}})
    return filters


async def get_evidence(
    dataset_version: str,
    page: int,
    page_size: int,
    product_id: str | None = None,
    aspect: str | None = None,
    sentiment: str | None = None,
    period: str | None = None,
) -> EvidenceResponse:
    """证据下钻：返回与聚合条件匹配的原始评论分页列表。"""
    body = {
        "query": {
            "bool": {
                "filter": _evidence_filters(
                    dataset_version, product_id, aspect, sentiment, period
                )
            }
        },
        "sort": [{"reviewed_at": {"order": "desc"}}],
        "from": (page - 1) * page_size,
        "size": page_size,
        # 深分页依赖精确 total（ES 默认 10000 截断会导致翻页按钮消失）
        "track_total_hits": True,
    }
    resp = await _search(body)
    items = [
        EvidenceItem(
            review_id=src["review_id"],
            product_id=src.get("product_id", ""),
            review_title=src.get("review_title"),
            review_text=src.get("review_text", ""),
            rating=src.get("rating"),
            reviewed_at=src.get("reviewed_at"),
            overall_sentiment=src.get("overall_sentiment"),
            aspects=src.get("aspects", []),
        )
        for hit in resp["hits"]["hits"]
        for src in (hit["_source"],)
    ]
    return EvidenceResponse(
        items=items,
        total=resp["hits"]["total"]["value"],
        page=page,
        page_size=page_size,
    )
