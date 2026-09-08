"""M1 扩展：users 增加 phone / username 登录标识

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-06

说明：一个账号绑定三种登录标识（邮箱 / 手机号 / 账号名）。
- phone：选填，中国大陆手机号，唯一
- username：注册时自动生成（邮箱前缀或随机串），唯一，可用于登录
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(length=20), nullable=True))
    op.add_column("users", sa.Column("username", sa.String(length=32), nullable=True))
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)
    op.create_index("ix_users_username", "users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_column("users", "username")
    op.drop_column("users", "phone")
