"""M5 人工审核工作流的请求/响应模型。

- ReviewTaskOut：任务详情（含关联的原始评论 quote，便于审核人员判断）。
- SubmitReviewRequest：运营提交审核结果（operator+）。
- SecondReviewRequest：二次复核（analyst+）。
- GenerateTasksRequest：从预测结果抽取审核任务（analyst+）。
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Sentiment = Literal["positive", "neutral", "negative"]

ReviewReason = Literal[
    "confirm_prediction",
    "correct_sentiment",
    "correct_aspects",
    "correct_both",
    "invalid_text",
    "insufficient_info",
]


# ---------- 审核任务 ----------


class ReviewTaskBase(BaseModel):
    id: str
    dataset_version: str
    review_id: str
    sampling_group: str
    sampling_reason: str | None = None
    system_sentiment: str | None = None
    system_confidence: float | None = None
    system_aspects: list[dict] | None = None
    model_version: str | None = None
    reviewer_sentiment: str | None = None
    reviewer_aspects: list[dict] | None = None
    review_reason: str | None = None
    review_note: str | None = None
    status: str
    reviewer_id: str | None = None
    reviewed_at: datetime | None = None
    second_reviewer_id: str | None = None
    second_reviewed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewTaskOut(ReviewTaskBase):
    """任务详情：额外携带原始评论摘要供审核判断。"""

    review_title: str | None = None
    review_text: str | None = None
    rating: int | None = None


class ReviewTaskListItem(ReviewTaskBase):
    pass


class ReviewTaskListResponse(BaseModel):
    items: list[ReviewTaskListItem]
    total: int
    page: int
    page_size: int


class SubmitReviewRequest(BaseModel):
    """提交一次审核结果。"""

    status: Literal["approved", "rejected"]
    reviewer_sentiment: Sentiment | None = None
    reviewer_aspects: list[dict] = Field(default_factory=list)
    review_reason: ReviewReason = "confirm_prediction"
    review_note: str | None = Field(default=None, max_length=2000)


class SecondReviewRequest(BaseModel):
    """二次复核：由 agnostic 分析师确认运营的审批结果。"""

    status: Literal["approved", "rejected"]
    review_note: str | None = Field(default=None, max_length=2000)


# ---------- 生成任务 ----------


class GenerateTasksRequest(BaseModel):
    dataset_version: str
    model_version: str | None = None
    count: int = Field(default=50, ge=1, le=5000)


class GenerateTasksResponse(BaseModel):
    created: int
    dataset_version: str
    skipped: int = 0


# ---------- 统计 ----------


class SummaryResponse(BaseModel):
    dataset_version: str | None = None
    total: int = 0
    done: int = 0
    pending: int = 0
    approved: int = 0
    verified: int = 0
    rejected: int = 0
    completion_rate: float = 0.0  # 0~1
    agreement_rate: float = 0.0  # 已审核中与系统预测一致的比例 0~1
