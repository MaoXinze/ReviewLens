"""Elasticsearch 异步客户端与索引工具。

Lazy 单例：应用启动时不强制连接 ES，仅在导入/搜索时实例化。
索引映射与架构设计说明书 §6.2 保持一致（review_text 等使用 IK 分词）。
"""
from elasticsearch import AsyncElasticsearch

from app.core.config import settings

_client: AsyncElasticsearch | None = None


def get_es() -> AsyncElasticsearch:
    """返回（并按需创建）全局异步 ES 客户端。"""
    global _client
    if _client is None:
        _client = AsyncElasticsearch(settings.elasticsearch_host)
    return _client


async def close_es() -> None:
    """关闭全局 ES 客户端（应用退出时调用）。"""
    global _client
    if _client is not None:
        await _client.close()
        _client = None


# 中文分词：text 用 ik_max_word 建索引，ik_smart 检索
TEXT_FIELD = {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart"}

REVIEWS_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "mappings": {
        "properties": {
            "dataset_version": {"type": "keyword"},
            "review_id": {"type": "keyword"},
            "product_id": {"type": "keyword"},
            "product_group_id": {"type": "keyword"},
            "review_title": TEXT_FIELD,
            "review_text": TEXT_FIELD,
            "rating": {"type": "integer"},
            "reviewed_at": {"type": "date"},
            "language": {"type": "keyword"},
            "helpful_votes": {"type": "integer"},
            "verified_purchase": {"type": "boolean"},
            # NLP 预测结果（M4/M6 写入），支持属性级搜索/聚合
            "overall_sentiment": {"type": "keyword"},
            "aspects": {
                "type": "nested",
                "properties": {
                    "aspect": {"type": "keyword"},
                    "sentiment": {"type": "keyword"},
                    "confidence": {"type": "float"},
                },
            },
            "model_version": {"type": "keyword"},
        }
    },
}


async def ensure_ik_analyzer() -> None:
    """校验 IK 分词器可用；缺插件时抛出带指引的异常（M3 搜索引擎前置检查）。"""
    es = get_es()
    try:
        await es.indices.analyze(body={"text": "电池续航测试", "analyzer": "ik_smart"})
    except Exception as exc:  # noqa: BLE001 - 统一转为可读的错误指引
        raise RuntimeError(
            "IK 分词器不可用：请确认 elasticsearch 镜像已内置 analysis-ik 插件"
            "（docker compose up -d 后重试）。"
        ) from exc


async def ensure_reviews_index() -> None:
    """确保 reviews 索引存在；不存在则创建（幂等）。"""
    es = get_es()
    if await es.indices.exists(index=settings.reviews_index):
        return
    await es.indices.create(index=settings.reviews_index, **REVIEWS_MAPPING)


def _doc_id(dataset_version: str, review_id: str) -> str:
    """ES _id：以 dataset_version 为命名空间，避免跨版本覆盖。"""
    return f"{dataset_version}|{review_id}"


async def bulk_index_reviews(docs: list[dict], dataset_version: str) -> None:
    """批量写入评论到 ES。docs 为规范化评论 dict 列表。"""
    if not docs:
        return
    es = get_es()
    operations: list[dict] = []
    for doc in docs:
        operations.append(
            {
                "index": {
                    "_index": settings.reviews_index,
                    "_id": _doc_id(dataset_version, doc["review_id"]),
                }
            }
        )
        operations.append(doc)
    await es.bulk(operations=operations)


async def update_review_predictions(
    dataset_version: str,
    predictions: list[dict],
    model_version: str,
) -> None:
    """批量回写 N 条预测到 ES 评论文档（overall_sentiment/aspects/model_version）。

    predictions 为 {review_id, overall_sentiment, confidence, aspects} 列表。
    """
    if not predictions:
        return
    es = get_es()
    operations: list[dict] = []
    for p in predictions:
        operations.append(
            {
                "update": {
                    "_index": settings.reviews_index,
                    "_id": _doc_id(dataset_version, p["review_id"]),
                }
            }
        )
        doc = {
            "overall_sentiment": p["overall_sentiment"],
            "aspects": p.get("aspects", []),
        }
        if model_version:
            doc["model_version"] = model_version
        operations.append({"doc": doc})
    await es.bulk(operations=operations)
