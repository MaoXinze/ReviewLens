"""M7 体验洞察看板请求/响应模型。"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# 趋势时间粒度：year 按年聚合；month 按年分组展示 12 个月；
# week 按月内周；day 按周内 7 天
Granularity = Literal["year", "month", "week", "day"]


class SentimentBucket(BaseModel):
    """情感分布分桶。"""

    overall_sentiment: str
    doc_count: int
    ratio: float


class ReviewProgress(BaseModel):
    """审核进度统计（总览卡）。"""

    total: int
    done: int
    pending: int
    approved: int
    verified: int
    rejected: int
    completion_rate: float
    agreement_rate: float


class AspectRate(BaseModel):
    """单属性差评率（含环比率）。"""

    aspect: str
    total: int
    negative: int
    negative_rate: float
    prev_rate: float | None = None
    change: float | None = None


class InsightOverView(BaseModel):
    """总览看板响应。"""

    dataset_version: str
    model_version: str | None = None
    generated_at: datetime
    total_reviews: int
    sentiment_distribution: list[SentimentBucket]
    top_negative_aspects: list[AspectRate]
    review_progress: ReviewProgress


class AspectRankingResponse(BaseModel):
    """属性差评率排行响应。"""

    dataset_version: str
    model_version: str | None = None
    generated_at: datetime
    filter_conditions: dict
    ranking: list[AspectRate]


class TrendPoint(BaseModel):
    """趋势时间序列点。"""

    bucket: str
    total: int
    negative: int
    negative_rate: float


class TrendsResponse(BaseModel):
    """趋势时间序列响应。"""

    dataset_version: str
    model_version: str | None = None
    granularity: Granularity
    period: str | None = None
    items: list[TrendPoint]


class SkuStat(BaseModel):
    """单个 SKU 对比统计。"""

    product_id: str
    total: int
    negative: int
    negative_rate: float
    top_aspects: list[AspectRate]


class SkuComparisonResponse(BaseModel):
    """SKU 对比响应。"""

    dataset_version: str
    model_version: str | None = None
    skus: list[SkuStat]


class EvidenceItem(BaseModel):
    """证据评论。"""

    review_id: str
    product_id: str
    review_title: str | None = None
    review_text: str
    rating: int | None = None
    reviewed_at: str | None = None
    overall_sentiment: str | None = None
    aspects: list[dict] = []


class EvidenceResponse(BaseModel):
    """证据下钻响应。"""

    items: list[EvidenceItem]
    total: int
    page: int
    page_size: int
