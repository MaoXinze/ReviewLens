"""初始化/升级管理员账号。

用法：python scripts/seed_admin.py
环境变量：
  ADMIN_EMAIL    （默认 admin@reviewlens.dev，注意不能使用 .local 等保留域名，
                  否则会被后端 EmailStr 校验拒绝）
  ADMIN_PASSWORD （默认随机生成并打印到终端）

逻辑：邮箱存在则升级为 admin + 启用；不存在则新建 admin 用户。
幂等：可重复执行。
"""
import asyncio
import os
import secrets
import sys
from pathlib import Path

# 将 backend 目录加入 sys.path，便于以包方式导入 app.*
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))


async def _run() -> str:
    from sqlalchemy import select

    from app.core.db import AsyncSessionLocal
    from app.core.security import hash_password
    from app.models.user import User, UserRole

    email = os.environ.get("ADMIN_EMAIL", "admin@reviewlens.dev").strip().lower()
    username = os.environ.get("ADMIN_USERNAME", "admin").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(12)

    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                username=username,
                password_hash=hash_password(password),
                full_name="系统管理员",
                role=UserRole.ADMIN.value,
                is_active=True,
            )
            db.add(user)
            action = "创建"
        else:
            user.role = UserRole.ADMIN.value
            user.is_active = True
            user.username = user.username or username
            action = "升级"
        await db.commit()

    return f"[seed_admin] {action}管理员账号：{email}（登录账号：{user.username}，密码：{password}）"


def main() -> int:
    print(asyncio.run(_run()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
