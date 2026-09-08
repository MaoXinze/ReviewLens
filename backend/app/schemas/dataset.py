"""M2 数据集 API 的请求/响应模型。"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DatasetImportResponse(BaseModel):
    job_id: str | None = None
    status: str
    message: str
    dataset_version: str | None = None
    reused: bool = False


class QualityReportItem(BaseModel):
    rejection_reasons: dict[str, int] = Field(default_factory=dict)
    reasons_detail: dict[str, list[str]] = Field(default_factory=dict)


class DatasetOut(BaseModel):
    dataset_version: str
    source_filename: str
    file_sha256: str
    total_rows: int
    valid_rows: int
    rejected_rows: int
    quality_report: dict[str, Any] | None = None
    status: str
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetListResponse(BaseModel):
    items: list[DatasetOut]
    total: int
    page: int
    page_size: int


class ReviewOut(BaseModel):
    id: str
    review_id: str
    product_id: str
    product_group_id: str | None = None
    review_title: str | None = None
    review_text: str
    rating: int | None = None
    reviewed_at: datetime
    reviewer_id: str | None = None
    helpful_votes: int = 0
    verified_purchase: bool = False
    language: str = "en"

    model_config = {"from_attributes": True}


class ReviewListResponse(BaseModel):
    items: list[ReviewOut]
    total: int
    page: int
    page_size: int
