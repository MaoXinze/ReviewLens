"""M8: 创建 issues 与 issue_history 表

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-03

说明：
- issues：问题卡，记录从看板洞察转化到的可追踪改进行动。
- issue_history：问题卡字段变更审计轨迹（谁/何时/改了什么/为什么）。
created_at / updated_at 使用 Python 侧默认写入。
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "issues",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("dataset_version", sa.String(100), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("aspect", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("description", sa.TEXT(), nullable=True),
        sa.Column("source_review_ids", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column(
            "assignee", sa.String(64), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("resolution_note", sa.TEXT(), nullable=True),
        sa.Column("validation_note", sa.TEXT(), nullable=True),
        sa.Column(
            "created_by", sa.String(64), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_issues_status", "issues", ["status"])
    op.create_index("ix_issues_aspect", "issues", ["aspect"])
    op.create_index("ix_issues_assignee", "issues", ["assignee"])

    op.create_table(
        "issue_history",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "issue_id", sa.String(64), sa.ForeignKey("issues.id"), nullable=False
        ),
        sa.Column("field_name", sa.String(50), nullable=False),
        sa.Column("old_value", sa.TEXT(), nullable=True),
        sa.Column("new_value", sa.TEXT(), nullable=True),
        sa.Column(
            "changed_by", sa.String(64), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.TEXT(), nullable=True),
    )
    op.create_index(
        "ix_issue_history_issue_id", "issue_history", ["issue_id", "changed_at"]
    )


def downgrade() -> None:
    op.drop_table("issue_history")
    op.drop_table("issues")