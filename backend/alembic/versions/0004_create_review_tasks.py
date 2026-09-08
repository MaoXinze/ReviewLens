"""M5: 创建 review_tasks 与 review_task_history 表

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-03

说明：
- review_tasks：人工审核任务，UNIQUE(dataset_version, review_id) 防止重复生成。
- review_task_history：审核变更审计轨迹。
created_at / changed_at 使用 Python 侧默认写入（M2 教训）。
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_tasks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("dataset_version", sa.String(100), nullable=False),
        sa.Column("review_id", sa.String(200), nullable=False),
        sa.Column("sampling_group", sa.String(50), nullable=False),
        sa.Column("sampling_reason", sa.String(200), nullable=True),
        sa.Column("system_sentiment", sa.String(20), nullable=True),
        sa.Column("system_confidence", sa.Float(), nullable=True),
        sa.Column("system_aspects", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("reviewer_sentiment", sa.String(20), nullable=True),
        sa.Column("reviewer_aspects", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("review_reason", sa.String(30), nullable=True),
        sa.Column("review_note", sa.TEXT(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "reviewer_id", sa.String(64), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "second_reviewer_id",
            sa.String(64),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("second_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint(
        "uq_review_tasks_dataset_review",
        "review_tasks",
        ["dataset_version", "review_id"],
    )
    op.create_index("ix_review_tasks_status", "review_tasks", ["status"])
    op.create_index(
        "ix_review_tasks_sampling_group", "review_tasks", ["sampling_group"]
    )

    op.create_table(
        "review_task_history",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "task_id", sa.String(64), sa.ForeignKey("review_tasks.id"), nullable=False
        ),
        sa.Column("field_name", sa.String(50), nullable=False),
        sa.Column("old_value", sa.TEXT(), nullable=True),
        sa.Column("new_value", sa.TEXT(), nullable=True),
        sa.Column(
            "changed_by", sa.String(64), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(30), nullable=True),
    )
    op.create_index(
        "ix_review_task_history_task_id", "review_task_history", ["task_id"]
    )


def downgrade() -> None:
    op.drop_table("review_task_history")
    op.drop_table("review_tasks")
