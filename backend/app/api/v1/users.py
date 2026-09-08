"""用户管理路由（管理员）。

- GET  /api/v1/users              用户列表
- PATCH /api/v1/users/{id}/role   修改用户角色
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role, write_audit_log
from app.core.db import get_db
from app.models.user import User, UserRole
from app.schemas.auth import RoleUpdate, UserOut

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("")
async def list_users(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN.value)),
) -> dict:
    """用户列表（仅 admin）。"""
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    total = await db.scalar(select(func.count()).select_from(User)) or 0
    items = await db.scalars(
        select(User)
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "code": 0,
        "data": {
            "items": [UserOut.model_validate(u) for u in items],
            "total": total or 0,
            "page": page,
            "page_size": page_size,
        },
    }


@router.patch("/{user_id}/role")
async def update_user_role(
    user_id: str,
    payload: RoleUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role(UserRole.ADMIN.value)),
) -> dict:
    """修改用户角色（仅 admin）。"""
    if payload.role not in {r.value for r in UserRole}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="无效角色"
        )

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    old_role = user.role
    user.role = payload.role
    await write_audit_log(
        db,
        action="update",
        resource_type="user",
        resource_id=user.id,
        details={"role": {"old": old_role, "new": payload.role}},
        user_id=admin.id,
    )
    await db.commit()
    await db.refresh(user)
    return {"code": 0, "data": UserOut.model_validate(user)}
