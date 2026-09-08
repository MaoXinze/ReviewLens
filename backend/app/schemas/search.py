"""M3 评论搜索引擎的请求/响应模型。

对齐 docs/modules/M3-评论搜索引擎.md 的 API 示例与架构设计 §7.2。
"""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

SortBy = Literal["relevance", "date", "helpful"]
GroupBy = Literal["aspect", "rating", "date", "sentiment"]
DateHistogram = Literal["day", "week", "month"]


class SearchFilters(BaseModel):
    """全文搜索的过滤条件（全部可选，多条件取交集）。"""

    dataset_version: str | None = None
    product_id: str | None = None
    product_group_id: str | None = None
    rating_min: int | None = Field(default=None, ge=1, le=5)
    rating_max: int | None = Field(default=None, ge=1, le=5)
    date_from: date | None = None
    date_to: date | None = None
    language: str | None = None
    overall_sentiment: str | None = None
    aspect: str | None = None


class SearchRequest(BaseModel):
    query: str = Field(
        default="", max_length=200, description="关键词（中英文均可，IK 分词）"
    )
    filters: SearchFilters = Field(default_factory=SearchFilters)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort_by: SortBy = "relevance"


class SearchHit(BaseModel):
    review_id: str
    product_id: str
    product_group_id: str | None = None
    review_title: str | None = None
    review_text: str
    rating: int | None = None
    reviewed_at: datetime | None = None
    language: str | None = None
    helpful_votes: int = 0
    verified_purchase: bool = False
    overall_sentiment: str | None = None
    highlight: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    items: list[SearchHit]
    total: int
    page: int
    page_size: int
    took_ms: int


class AggregateFilters(BaseModel):
    """聚合查询的过滤条件（不含 dataset_version，它在请求体顶层）。"""

    product_id: str | None = None
    product_group_id: str | None = None
    rating_min: int | None = Field(default=None, ge=1, le=5)
    rating_max: int | None = Field(default=None, ge=1, le=5)
    date_from: date | None = None
    date_to: date | None = None
    language: str | None = None


class AggregateRequest(BaseModel):
    dataset_version: str | None = None
    group_by: GroupBy = "aspect"
    date_histogram: DateHistogram = "week"
    filters: AggregateFilters = Field(default_factory=AggregateFilters)


class AggregateBucket(BaseModel):
    key: str
    doc_count: int
    negative_count: int = 0
    negative_rate: float = 0.0
    positive_count: int | None = None
    neutral_count: int | None = None
    avg_confidence: float | None = None


class AggregateResponse(BaseModel):
    buckets: list[AggregateBucket]
    total_docs: int
    took_ms: int
