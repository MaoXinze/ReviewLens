"""Review 规范化评论 ORM 模型（按 reviewed_at 做范围分区）。

数据量大的核心表采用 RANGE 分区；默认分区 reviews_default 通过迁移/建表
SQL 显式创建（DEFAULT PARTITION）。复合主键 (id, reviewed_at) 需包含分区键。
PG 不允许全局 UNIQUE 约束不含分区键，故 (dataset_version, review_id) 的唯一性
由导入阶段按数据集去重保证（见 services/validation.py）。
created_at 使用 Python 侧默认，避免 asyncpg 批量插入 RETURNING 兼容问题。
"""
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        PrimaryKeyConstraint("id", "reviewed_at"),
        {
            "postgresql_partition_by": "RANGE (reviewed_at)",
            "comment": "评论表，按 reviewed_at 范围分区",
        },
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    dataset_version: Mapped[str] = mapped_column(
        String(100), ForeignKey("datasets.dataset_version"), nullable=False
    )
    review_id: Mapped[str] = mapped_column(String(200), nullable=False)
    product_id: Mapped[str] = mapped_column(String(100), nullable=False)
    product_group_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    review_title: Mapped[str | None] = mapped_column(nullable=True)
    review_text: Mapped[str] = mapped_column(nullable=False)
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    reviewer_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    helpful_votes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verified_purchase: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
