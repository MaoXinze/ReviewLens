"""M4: 创建 review_predictions 与 analysis_runs 表

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-03

说明：review_predictions 非分区表，可添加 (dataset_version, review_id, model_version)
唯一约束，保证同一评论+模型仅保存一条预测。created_at 用 Python 侧默认写入。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_predictions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("dataset_version", sa.String(100), nullable=False),
        sa.Column("review_id", sa.String(200), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("overall_sentiment", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("aspects", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # 唯一约束
    op.create_unique_constraint(
        "uq_review_predictions_version_review_model",
        "review_predictions",
        ["dataset_version", "review_id", "model_version"],
    )
    op.create_index(
        "ix_review_predictions_dataset_version",
        "review_predictions",
        ["dataset_version"],
    )
    op.create_index(
        "ix_review_predictions_model_version",
        "review_predictions",
        ["model_version"],
    )
    op.create_index(
        "idx_predictions_low_conf",
        "review_predictions",
        ["confidence"],
        postgresql_where=sa.text("confidence < 0.7"),
    )

    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("dataset_version", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("algorithm", sa.String(30), nullable=False, server_default="tfidf_lr"),
        sa.Column("random_seed", sa.Integer(), nullable=False, server_default="42"),
        sa.Column("train_samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("test_samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("macro_f1", sa.Float(), nullable=True),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("classification_report", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("confusion_matrix", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("model_file_sha256", sa.String(64), nullable=True),
        sa.Column("model_file_path", sa.String(500), nullable=True),
        sa.Column("publish_status", sa.String(20), nullable=False, server_default="evaluation_only"),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(64), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint(
        "uq_analysis_runs_model_version", "analysis_runs", ["model_version"]
    )
    op.create_index("ix_analysis_runs_dataset_version", "analysis_runs", ["dataset_version"])
    op.create_index("ix_analysis_runs_status", "analysis_runs", ["status"])
    op.create_index("ix_analysis_runs_publish_status", "analysis_runs", ["publish_status"])


def downgrade() -> None:
    op.drop_table("analysis_runs")
    op.drop_table("review_predictions")