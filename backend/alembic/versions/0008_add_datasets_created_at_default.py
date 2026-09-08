"""M6-fix: datasets.created_at 补充 server_default

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-03

说明：Dataset 模型将 created_at 声明为 server_default=func.now()，但迁移 0002
建表时未给 datasets.created_at 设置 DB 默认值，导致 INSERT 时该列被省略、
PG 按 NOT NULL 报错。补充 server_default 与上层保持一致。
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "datasets",
        "created_at",
        server_default=sa.text("now()"),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "datasets",
        "created_at",
        server_default=None,
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )