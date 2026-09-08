"""M2: 创建 datasets 与 reviews（范围分区）表

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-03

说明：reviews 采用 RANGE 分区，PG 要求分区键必须包含在唯一约束内，因此
(dataset_version, review_id) 的唯一性由导入阶段的按数据集去重保证。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- datasets ----
    op.create_table(
        "datasets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("dataset_version", sa.String(100), nullable=False),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("field_mapping", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quality_report", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column("created_by", sa.String(64), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_datasets_dataset_version", "datasets", ["dataset_version"], unique=True
    )
    op.create_index("idx_datasets_status", "datasets", ["status"])
    op.create_index("idx_datasets_created", "datasets", ["created_at"])

    # ---- reviews（按 reviewed_at 范围分区，含 DEFAULT 分区）----
    op.execute(
        """
        CREATE TABLE reviews (
            id                VARCHAR(64) NOT NULL,
            dataset_version   VARCHAR(100) NOT NULL REFERENCES datasets(dataset_version),
            review_id         VARCHAR(200) NOT NULL,
            product_id        VARCHAR(100) NOT NULL,
            product_group_id  VARCHAR(100),
            review_title      TEXT,
            review_text       TEXT NOT NULL,
            rating            SMALLINT,
            reviewed_at       TIMESTAMPTZ NOT NULL,
            reviewer_id       VARCHAR(200),
            helpful_votes     INTEGER NOT NULL DEFAULT 0,
            verified_purchase BOOLEAN NOT NULL DEFAULT FALSE,
            language          VARCHAR(10) NOT NULL DEFAULT 'en',
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, reviewed_at)
        ) PARTITION BY RANGE (reviewed_at)
        """
    )
    op.execute("CREATE TABLE reviews_default PARTITION OF reviews DEFAULT")
    op.create_index("idx_reviews_dataset", "reviews", ["dataset_version"])
    op.create_index("idx_reviews_product", "reviews", ["product_id"])
    op.create_index("idx_reviews_reviewed", "reviews", ["reviewed_at"])


def downgrade() -> None:
    op.drop_table("reviews")
    op.drop_table("datasets")