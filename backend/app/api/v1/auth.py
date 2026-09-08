"""认证路由。

- POST  /api/auth/register   注册（邮箱或手机号其一；账号名缺省自动生成）
- POST  /api/auth/login      登录（邮箱 / 手机号 / 账号名 任一 + 密码）
- GET   /api/auth/me         当前用户信息
- PUT   /api/auth/me         更新自己的 full_name
- POST  /api/auth/refresh    用 refresh_token 换新 access_token
"""
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, write_audit_log
from app.core.config import settings
from app.core.db import get_db
from app.core.rate_limit import SlidingWindowLimiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User, UserRole
from app.schemas.auth import (
    PHONE_RE,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenResponse,
    UserOut,
    UserUpdateMe,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 登录防爆破：账号维度（IP+标识）与 IP 维度（防扫号）双层限流；注册按 IP 限频
account_limiter = SlidingWindowLimiter(
    settings.login_max_failures, settings.auth_rate_window_seconds
)
ip_limiter = SlidingWindowLimiter(
    settings.login_ip_max_failures, settings.auth_rate_window_seconds
)
register_limiter = SlidingWindowLimiter(
    settings.login_ip_max_failures, settings.auth_rate_window_seconds
)


def _too_many_requests(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="尝试过于频繁，请稍后再试",
        headers={"Retry-After": str(retry_after)},
    )


def _client_ip(request: Request) -> str | None:
    """优先取 X-Forwarded-For，否则用请求方地址。"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


def _generate_username(email: str | None = None, phone: str | None = None) -> str:
    """自动生成全数字账号名：9 开头 8 位（不会与 11 位手机号格式冲突）。

    唯一性由调用方的查重 + IntegrityError 重试保证。
    """
    return "9" + "".join(secrets.choice("0123456789") for _ in range(7))


async def _resolve_user(db: AsyncSession, identifier: str) -> User | None:
    """按登录标识查用户：@ → 邮箱；1 开头 11 位数字 → 手机号；其余 → 账号名。"""
    if "@" in identifier:
        return await db.scalar(select(User).where(User.email == identifier))
    if PHONE_RE.fullmatch(identifier):
        return await db.scalar(select(User).where(User.phone == identifier))
    return await db.scalar(select(User).where(User.username == identifier))


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """注册新用户（邮箱或手机号其一），默认角色 operator；账号名缺省自动生成。"""
    ip = _client_ip(request) or "unknown"
    reg_key = f"register:{ip}"
    blocked, retry_after = register_limiter.is_blocked(reg_key)
    if blocked:
        raise _too_many_requests(retry_after)
    register_limiter.record(reg_key)  # 按尝试计数，防批量建号

    email = payload.email.lower() if payload.email else None
    phone = payload.phone or None
    username = (payload.username or _generate_username(email, phone)).lower()

    # users.email 为 NOT NULL：纯手机号注册时合成占位邮箱（登录走 phone 标识）
    if email is None and phone:
        email = f"{phone}@phone.reviewlens.dev"

    # 自定义账号名查重
    if payload.username:
        existing = await db.scalar(select(User).where(User.username == username))
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="账号名已被占用"
            )

    user = User(
        email=email,
        phone=phone,
        username=username,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        role=UserRole.OPERATOR.value,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # 唯一约束冲突（邮箱/手机号/自动账号名撞名）：自动生成撞名时重试一次
        if not payload.username:
            user.username = _generate_username(email, phone)
            db.add(user)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="邮箱或手机号已被注册"
                ) from None
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="邮箱、手机号或账号名已被注册",
            ) from None
    await db.refresh(user)

    return {
        "code": 0,
        "data": RegisterResponse(
            id=user.id,
            email=user.email,
            phone=user.phone,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
        ),
    }


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """登录：邮箱/手机号/账号名 任一 + 密码；失败计入围窗口限流。"""
    ip = _client_ip(request) or "unknown"
    identifier = payload.identifier
    account_key = f"login:acct:{ip}:{identifier}"
    ip_key = f"login:ip:{ip}"
    for key, limiter in ((account_key, account_limiter), (ip_key, ip_limiter)):
        blocked, retry_after = limiter.is_blocked(key)
        if blocked:
            raise _too_many_requests(retry_after)

    user = await _resolve_user(db, identifier)
    if user is None or not verify_password(payload.password, user.password_hash):
        account_limiter.record(account_key)
        ip_limiter.record(ip_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="账号或密码错误"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用"
        )

    account_limiter.reset(account_key)
    ip_limiter.reset(ip_key)

    await write_audit_log(
        db,
        action="login",
        user_id=user.id,
        resource_type="user",
        resource_id=user.id,
        ip_address=ip if ip != "unknown" else None,
    )
    await db.commit()

    return {
        "code": 0,
        "data": TokenResponse(
            access_token=create_access_token(user.id, user.role),
            refresh_token=create_refresh_token(user.id, user.role),
            expires_in=settings.access_token_expire_minutes * 60,
        ),
    }


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)) -> dict:
    """返回当前登录用户信息。"""
    return {"code": 0, "data": UserOut.model_validate(user)}


@router.put("/me")
async def update_me(
    payload: UserUpdateMe,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """更新自己的 full_name。"""
    if payload.full_name is not None:
        user.full_name = payload.full_name
        await db.commit()
        await db.refresh(user)
    return {"code": 0, "data": UserOut.model_validate(user)}


@router.post("/refresh")
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """用 refresh_token 换取新的 access_token。"""
    try:
        claims = decode_token(payload.refresh_token)
        if claims.get("type") != "refresh":
            raise JWTError("令牌类型错误")
        user_id = claims.get("sub")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="无效或过期的刷新令牌"
        ) from None

    user = await db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已被禁用"
        )

    return {
        "code": 0,
        "data": TokenResponse(
            access_token=create_access_token(user.id, user.role),
            refresh_token=payload.refresh_token,
            expires_in=settings.access_token_expire_minutes * 60,
        ),
    }
