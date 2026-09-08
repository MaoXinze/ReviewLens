"""M9: 创建 alert_rules、alerts 与 export_records 表

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-03

说明：
- alert_rules：告警规则（threshold 阈值 / trend 环比增长），支持按 SKU、窗口天数、去重天数。
- alerts：告警记录，状态机 active → acknowledged → resolved。
- export_records：CSV 导出记录（筛选条件 JSONB + MinIO 路径）。
created_at / triggered_at 使用 Python 侧默认写入。
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("rule_type", sa.String(20), nullable=False),
        sa.Column("aspect", sa.String(50), nullable=False),
        sa.Column("product_id", sa.String(100), nullable=True),
        sa.Column("threshold_value", sa.Float(), nullable=False),
        sa.Column("time_window_days", sa.Integer(), nullable=False),
        sa.Column("dedup_days", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "created_by", sa.String(64), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alert_rules_status", "alert_rules", ["status"])
    op.create_index("ix_alert_rules_aspect", "alert_rules", ["aspect"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "rule_id", sa.String(64), sa.ForeignKey("alert_rules.id"), nullable=False
        ),
        sa.Column("aspect", sa.String(50), nullable=False),
        sa.Column("product_id", sa.String(100), nullable=True),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("trigger_value", sa.Float(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "resolved_by", sa.String(64), sa.ForeignKey("users.id"), nullable=True
        ),
    )
    op.create_index("ix_alerts_status", "alerts", ["status"])
    op.create_index("ix_alerts_rule", "alerts", ["rule_id"])

    op.create_table(
        "export_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "exported_by", sa.String(64), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("dataset_version", sa.String(100), nullable=False),
        sa.Column("filters", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_export_records_exported_by", "export_records", ["exported_by"]
    )


def downgrade() -> None:
    op.drop_table("export_records")
    op.drop_table("alerts")
    op.drop_table("alert_rules")