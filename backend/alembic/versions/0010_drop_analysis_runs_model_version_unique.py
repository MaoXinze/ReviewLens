"""M6 修复：删除 analysis_runs.model_version 唯一约束

Revision ID: 0010
Revises: 0008 → 0009
Create Date: 2026-09-06

说明：model_version 由「训练数据+seed」哈希生成（可复现设计），同一数据集
用相同 seed 重训必然产生相同版本号，唯一约束 uq_analysis_runs_model_version
会导致重训撞键 500。改为普通索引，允许多次训练引用同一版本。
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_analysis_runs_model_version", "analysis_runs", type_="unique"
    )
    op.create_index(
        "ix_analysis_runs_model_version", "analysis_runs", ["model_version"]
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_runs_model_version", table_name="analysis_runs")
    op.create_unique_constraint(
        "uq_analysis_runs_model_version", "analysis_runs", ["model_version"]
    )
