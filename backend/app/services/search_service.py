"""M3 评论搜索引擎服务：查询构建 + 搜索/聚合执行。

不新建数据库表，全部基于 Elasticsearch 索引（settings.reviews_index）。
查询结构对齐 docs/modules/M3-评论搜索引擎.md 的技术设计（IK 分词、高亮、分面聚合）。
"""
from time import perf_counter

from elasticsearch.exceptions import TransportError

from app.core.config import settings
from app.core.es import get_es
from app.schemas.search import (
    AggregateBucket,
    AggregateRequest,
    AggregateResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
)

# 全文检索字段：标题权重高于正文
_SEARCH_FIELDS = ["review_title^2", "review_text"]
# ES max_result_window 默认 10000，深翻页直接拒绝（引导用户收窄条件）
_MAX_FROM = 10000


class SearchUnavailable(Exception):
    """ES 不可用或查询失败，路由层转为 503。"""


def build_search_query(request: SearchRequest) -> dict:
    """构建全文搜索请求体（multi_match + IK 分词 + 过滤 + 高亮 + 分页排序）。"""
    must: list[dict] = []
    if request.query:
        must.append(
            {
                "multi_match": {
                    "query": request.query,
                    "fields": _SEARCH_FIELDS,
                    "analyzer": "ik_smart",
                }
            }
        )

    body: dict = {
        "query": {"bool": {"must": must, "filter": _build_filters(request.filters)}}
    }

    if request.sort_by == "date":
        body["sort"] = [{"reviewed_at": {"order": "desc"}}]
    elif request.sort_by == "helpful":
        body["sort"] = [{"helpful_votes": {"order": "desc"}}]

    body["highlight"] = {
        "fields": {
            "review_title": {"number_of_fragments": 0},
            "review_text": {"fragment_size": 200, "number_of_fragments": 3},
        },
        "pre_tags": ["<em>"],
        "post_tags": ["</em>"],
    }
    body["from"] = (request.page - 1) * request.page_size
    body["size"] = request.page_size
    # 深分页依赖精确 total（ES 默认 10000 截断会导致翻页失真）
    body["track_total_hits"] = True
    return body


def _build_filters(filters: object) -> list[dict]:
    """把过滤条件拼成 ES filter 子句列表（term/range/nested）。"""
    result: list[dict] = []
    for field in ("dataset_version", "product_id", "product_group_id", "language",
                  "overall_sentiment"):
        value = getattr(filters, field, None)
        if value is not None:
            result.append({"term": {field: value}})

    if filters.rating_min is not None or filters.rating_max is not None:
        rng: dict = {}
        if filters.rating_min is not None:
            rng["gte"] = filters.rating_min
        if filters.rating_max is not None:
            rng["lte"] = filters.rating_max
        result.append({"range": {"rating": rng}})

    if filters.date_from is not None or filters.date_to is not None:
        rng = {}
        if filters.date_from is not None:
            rng["gte"] = filters.date_from.isoformat()
        if filters.date_to is not None:
            rng["lte"] = filters.date_to.isoformat()
        result.append({"range": {"reviewed_at": rng}})

    aspect = getattr(filters, "aspect", None)
    if aspect is not None:
        result.append(
            {
                "nested": {
                    "path": "aspects",
                    "query": {"term": {"aspects.aspect": aspect}},
                }
            }
        )
    return result


def build_aggregation_query(request: AggregateRequest) -> dict:
    """构建分面聚合请求体（group_by: aspect | rating | date | sentiment）。"""
    filters: list[dict] = []
    if request.dataset_version:
        filters.append({"term": {"dataset_version": request.dataset_version}})
    f = request.filters
    if f.product_id:
        filters.append({"term": {"product_id": f.product_id}})
    if f.product_group_id:
        filters.append({"term": {"product_group_id": f.product_group_id}})
    if f.rating_min is not None or f.rating_max is not None:
        rng: dict = {}
        if f.rating_min is not None:
            rng["gte"] = f.rating_min
        if f.rating_max is not None:
            rng["lte"] = f.rating_max
        filters.append({"range": {"rating": rng}})
    if f.date_from is not None or f.date_to is not None:
        rng = {}
        if f.date_from is not None:
            rng["gte"] = f.date_from.isoformat()
        if f.date_to is not None:
            rng["lte"] = f.date_to.isoformat()
        filters.append({"range": {"reviewed_at": rng}})
    if f.language:
        filters.append({"term": {"language": f.language}})

    body: dict = {
        "size": 0,
        "query": {"bool": {"filter": filters}},
        # 精确 total：ES 默认 10000 截断会让分面统计的分母失真
        "track_total_hits": True,
    }

    if request.group_by == "aspect":
        body["aggs"] = {
            "aspects": {
                "nested": {"path": "aspects"},
                "aggs": {
                    "aspect_names": {
                        "terms": {"field": "aspects.aspect", "size": 50},
                        "aggs": {
                            "sentiments": {"terms": {"field": "aspects.sentiment"}},
                            "avg_confidence": {"avg": {"field": "aspects.confidence"}},
                        },
                    }
                },
            }
        }
    elif request.group_by == "rating":
        body["aggs"] = {
            "ratings": {
                "terms": {"field": "rating", "size": 5},
                "aggs": {
                    "negative": {"filter": {"term": {"overall_sentiment": "negative"}}}
                },
            }
        }
    elif request.group_by == "date":
        body["aggs"] = {
            "dates": {
                "date_histogram": {
                    "field": "reviewed_at",
                    "calendar_interval": request.date_histogram,
                },
                "aggs": {
                    "negative": {"filter": {"term": {"overall_sentiment": "negative"}}}
                },
            }
        }
    else:  # sentiment
        body["aggs"] = {
            "sentiments": {"terms": {"field": "overall_sentiment", "size": 5}}
        }
    return body


async def search_reviews(request: SearchRequest) -> SearchResponse:
    """执行全文搜索并返回带高亮的结果。"""
    body = build_search_query(request)
    if body["from"] + body["size"] > _MAX_FROM:
        raise ValueError("请求页码过深（超过 ES 窗口 10000 条），请缩小 page/page_size")

    started = perf_counter()
    try:
        resp = await get_es().search(index=settings.reviews_index, body=body)
    except TransportError as exc:
        raise SearchUnavailable(f"ES 搜索失败: {exc}") from exc
    took_ms = int((perf_counter() - started) * 1000)

    items = []
    for hit in resp["hits"]["hits"]:
        src = hit["_source"]
        items.append(
            SearchHit(
                review_id=src["review_id"],
                product_id=src.get("product_id", ""),
                product_group_id=src.get("product_group_id"),
                review_title=src.get("review_title"),
                review_text=src.get("review_text", ""),
                rating=src.get("rating"),
                reviewed_at=src.get("reviewed_at"),
                language=src.get("language"),
                helpful_votes=src.get("helpful_votes", 0),
                verified_purchase=src.get("verified_purchase", False),
                overall_sentiment=src.get("overall_sentiment"),
                highlight=_extract_highlight(hit.get("highlight", {})),
            )
        )
    return SearchResponse(
        items=items,
        total=resp["hits"]["total"]["value"],
        page=request.page,
        page_size=request.page_size,
        took_ms=took_ms,
    )


def _extract_highlight(highlight: dict) -> list[str]:
    """把 ES 高亮片段合并成列表（标题在前，正文在后）。"""
    fragments: list[str] = []
    for field in ("review_title", "review_text"):
        fragments.extend(highlight.get(field, []))
    return fragments


async def aggregate_reviews(request: AggregateRequest) -> AggregateResponse:
    """执行分面聚合，返回属性差评率等分桶。"""
    body = build_aggregation_query(request)
    started = perf_counter()
    try:
        resp = await get_es().search(index=settings.reviews_index, body=body)
    except TransportError as exc:
        raise SearchUnavailable(f"ES 聚合失败: {exc}") from exc
    took_ms = int((perf_counter() - started) * 1000)

    return AggregateResponse(
        buckets=_parse_buckets(request.group_by, resp.get("aggregations", {})),
        total_docs=resp["hits"]["total"]["value"],
        took_ms=took_ms,
    )


def _parse_buckets(group_by: str, aggs: dict) -> list[AggregateBucket]:
    """把 ES 聚合结果解析为统一的分桶模型。"""
    if group_by == "aspect":
        out = []
        for b in aggs.get("aspects", {}).get("aspect_names", {}).get("buckets", []):
            counts = {
                s["key"]: s["doc_count"]
                for s in b.get("sentiments", {}).get("buckets", [])
            }
            total = b["doc_count"] or 0
            neg = counts.get("negative", 0)
            out.append(
                AggregateBucket(
                    key=b["key"],
                    doc_count=total,
                    negative_count=neg,
                    negative_rate=round(neg / total, 4) if total else 0.0,
                    positive_count=counts.get("positive"),
                    neutral_count=counts.get("neutral"),
                    avg_confidence=b.get("avg_confidence", {}).get("value"),
                )
            )
        return out

    if group_by in ("rating", "date"):
        agg_name = "ratings" if group_by == "rating" else "dates"
        out = []
        for b in aggs.get(agg_name, {}).get("buckets", []):
            total = b["doc_count"]
            neg = b.get("negative", {}).get("doc_count", 0)
            out.append(
                AggregateBucket(
                    key=str(b.get("key_as_string", b["key"])),
                    doc_count=total,
                    negative_count=neg,
                    negative_rate=round(neg / total, 4) if total else 0.0,
                )
            )
        return out

    if group_by == "sentiment":
        out = []
        for b in aggs.get("sentiments", {}).get("buckets", []):
            total = b["doc_count"]
            is_neg = b["key"] == "negative"
            out.append(
                AggregateBucket(
                    key=b["key"],
                    doc_count=total,
                    negative_count=total if is_neg else 0,
                    negative_rate=1.0 if is_neg else 0.0,
                )
            )
        return out

    return []
