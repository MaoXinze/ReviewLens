"""User 用户 ORM 模型。

角色：admin（管理员）/ analyst（分析师）/ operator（运营）。
密码只存 bcrypt 哈希，绝不返回明文。
"""
from enum import StrEnum

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin


class UserRole(StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    OPERATOR = "operator"


class User(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    # 手机号（选填，中国大陆手机号；唯一索引见迁移 0011）
    phone: Mapped[str | None] = mapped_column(
        String(20), unique=True, index=True, nullable=True
    )
    # 登录账号（注册时按邮箱前缀/随机串自动生成，可用「账号 + 密码」登录）
    username: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True, nullable=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserRole.OPERATOR.value
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
