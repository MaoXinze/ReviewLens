"""M6 模型管理请求/响应模型。"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ReviewedTrainingRequest(BaseModel):
    """使用 approved/verified 人工审核样本触发训练。"""

    dataset_version: str
    algorithm: str = "tfidf_lr"
    min_samples: int | None = None


class ModelOut(BaseModel):
    """模型版本摘要（用于历史 / 当前模型）。"""

    id: str
    dataset_version: str
    model_version: str
    algorithm: str
    random_seed: int
    macro_f1: float | None = None
    accuracy: float | None = None
    test_samples: int
    status: str
    publish_status: str
    created_at: datetime
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}


class ModelHistoryResponse(BaseModel):
    items: list[ModelOut]
    total: int


class PublishModelResponse(BaseModel):
    status: str  # published / unchanged
    message: str
    model_version: str


class RollbackModelResponse(BaseModel):
    message: str
    previous_model_version: str | None
    has_previous: bool


class CurrentModelResponse(BaseModel):
    model_version: str | None = None
    algorithm: str | None = None
    macro_f1: float | None = None
    publish_status: str | None = None


class PublishCriteriaResponse(BaseModel):
    """发布会话门槛检查结果（供前端在发布前展示原因）。"""

    macro_f1: float | None = None
    macro_f1_ok: bool = False
    test_samples: int = 0
    test_samples_ok: bool = False
    coverage: float | None = None
    coverage_ok: bool = False
    can_publish: bool = False
    reasons: list[str] = []
    metrics: dict[str, Any] | None = None
