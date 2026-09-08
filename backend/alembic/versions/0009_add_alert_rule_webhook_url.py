"""M9: alert_rules 增加 webhook_url 列（告警通知渠道）

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-05

说明：为告警规则增加可选 webhook_url，触发告警时向该地址 POST JSON 通知。
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "alert_rules",
        sa.Column("webhook_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alert_rules", "webhook_url")
