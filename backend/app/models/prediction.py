"""NLP 预测结果与训练运行 ORM 模型（M4）。

- review_predictions：每条评论一行，
  唯一约束 (dataset_version, review_id, model_version)。
- analysis_runs：训练/分析运行记录，含发布门槛相关的指标与发布状态。
created_at 使用 Python 侧默认，
规避 asyncpg 批量 INSERT...RETURNING 兼容问题（M2 教训）。
"""
from datetime import UTC, datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReviewPrediction(Base):
    """NLP 预测结果表。"""

    __tablename__ = "review_predictions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_version: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    review_id: Mapped[str] = mapped_column(String(200), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    overall_sentiment: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    aspects: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint(
            "dataset_version",
            "review_id",
            "model_version",
            name="uq_review_predictions_version_review_model",
        ),
    )


class AnalysisRun(Base):
    """训练/分析运行记录。"""

    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_version: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    # 版本号由「训练数据+seed」哈希生成（可复现设计）：同一数据集重训会产生
    # 相同版本，因此不设唯一约束（见迁移 0010），多次训练可引用同一版本
    model_version: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )
    algorithm: Mapped[str] = mapped_column(
        String(30), nullable=False, default="tfidf_lr"
    )
    random_seed: Mapped[int] = mapped_column(Integer, nullable=False, default=42)
    train_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    test_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    macro_f1: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confusion_matrix: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queued", index=True
    )  # queued/running/succeeded/failed
    model_file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publish_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="evaluation_only", index=True
    )  # evaluation_only/published/archived
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
