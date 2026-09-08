"""安全工具：bcrypt 密码哈希 + JWT 签发/验证。

- 密码使用 passlib + bcrypt，rounds=12
- access_token：有效期由配置决定，payload 含 sub(user_id)/role/type/exp
- refresh_token：仅用于刷新 access_token，type=refresh
- 密钥从环境变量注入，缺失时由 config.ensure_security 在启动期拦截
"""
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """对明文密码做 bcrypt 哈希（rounds=12）。"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与哈希是否匹配。"""
    return pwd_context.verify(plain_password, hashed_password)


def _create_token(
    subject: str, role: str, expires_delta: timedelta, token_type: str
) -> str:
    """签发 JWT。subject 为 user_id 的字符串形式。"""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def create_access_token(user_id: str, role: str) -> str:
    return _create_token(
        user_id,
        role,
        timedelta(minutes=settings.access_token_expire_minutes),
        token_type="access",
    )


def create_refresh_token(user_id: str, role: str) -> str:
    return _create_token(
        user_id,
        role,
        timedelta(days=settings.refresh_token_expire_days),
        token_type="refresh",
    )


def decode_token(token: str) -> dict[str, Any]:
    """解码并校验 JWT，非法/过期抛 JWTError。"""
    return jwt.decode(
        token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
    )
