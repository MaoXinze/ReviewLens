"""M4 预测与训练运行的请求/响应模型。"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Sentiment = Literal["positive", "neutral", "negative"]


# ---------- 预测 ----------


class PredictionOut(BaseModel):
    review_id: str
    dataset_version: str
    model_version: str
    overall_sentiment: str
    confidence: float
    aspects: list[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


class PredictionListResponse(BaseModel):
    items: list[PredictionOut]
    total: int
    page: int
    page_size: int


class BatchInferenceRequest(BaseModel):
    """触发一批评论的批量推理。"""

    dataset_version: str
    model_version: str | None = None


class BatchInferenceResponse(BaseModel):
    status: str
    message: str
    dataset_version: str
    model_version: str | None = None
    job_id: str | None = None


class LowConfidenceOut(BaseModel):
    review_id: str
    overall_sentiment: str
    confidence: float
    aspects: list[dict]
    model_version: str
    dataset_version: str

    model_config = {"from_attributes": True}


# ---------- 训练运行 ----------


class CreateAnalysisRunRequest(BaseModel):
    dataset_version: str
    algorithm: Literal["tfidf_lr", "bert_base"] = "tfidf_lr"
    min_samples: int | None = Field(default=None, ge=1)


class AnalysisRunOut(BaseModel):
    id: str
    dataset_version: str
    model_version: str
    algorithm: str
    random_seed: int
    train_samples: int
    test_samples: int
    macro_f1: float | None = None
    accuracy: float | None = None
    classification_report: dict[str, Any] | None = None
    confusion_matrix: list[list[int]] | dict[str, Any] | None = None
    status: str
    publish_status: str
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnalysisRunListResponse(BaseModel):
    items: list[AnalysisRunOut]
    total: int
    page: int
    page_size: int


class PublishResponse(BaseModel):
    status: str
    message: str
    model_version: str


class CurrentModelResponse(BaseModel):
    model_version: str | None = None
    algorithm: str | None = None
    macro_f1: float | None = None
    status: str | None = None
