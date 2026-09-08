"""人工审核工作流 ORM 模型（M5）。

- review_tasks：一条待人工审核的评论，携带系统预测（不可修改）+ 人工审核结果。
- review_task_history：审核过程中每次字段变更的审计轨迹，
  记录「谁、何时、改了什么、为什么」（满足验收标准 4）。
注意：review_tasks 建立 (dataset_version, review_id) 唯一约束，
同一条评论在同一数据集内只能存在一条审核任务。
"""
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# 审核任务状态机取值
REVIEW_STATUS_PENDING = "pending"
REVIEW_STATUS_APPROVED = "approved"
REVIEW_STATUS_VERIFIED = "verified"
REVIEW_STATUS_REJECTED = "rejected"
VALID_REVIEW_STATUSES = {
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_VERIFIED,
    REVIEW_STATUS_REJECTED,
}

# 采样组
SAMPLE_GROUP_LOW_CONFIDENCE = "low_confidence"
SAMPLE_GROUP_HIGH_RISK = "high_risk"
SAMPLE_GROUP_RANDOM = "random"

# 审核理由枚举
REVIEW_REASONS = {
    "confirm_prediction",  # 认可系统预测
    "correct_sentiment",   # 修正情感
    "correct_aspects",     # 修正属性
    "correct_both",        # 情感+属性都修正
    "invalid_text",        # 无效文本
    "insufficient_info",   # 信息不足
}


class ReviewTask(Base):
    """人工审核任务。"""

    __tablename__ = "review_tasks"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid4())
    )
    dataset_version: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    review_id: Mapped[str] = mapped_column(String(200), nullable=False)
    sampling_group: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    sampling_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # 系统预测（只读）
    system_sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    system_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    system_aspects: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # 人工审核
    reviewer_sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reviewer_aspects: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    review_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)
    review_note: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=REVIEW_STATUS_PENDING, index=True
    )
    reviewer_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    second_reviewer_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id"), nullable=True
    )
    second_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint(
            "dataset_version", "review_id", name="uq_review_tasks_dataset_review"
        ),
    )


class ReviewTaskHistory(Base):
    """审核任务变更审计轨迹。"""

    __tablename__ = "review_task_history"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: str(uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("review_tasks.id"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value: Mapped[str | None] = mapped_column(nullable=True)
    new_value: Mapped[str | None] = mapped_column(nullable=True)
    changed_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    reason: Mapped[str | None] = mapped_column(String(30), nullable=True)
