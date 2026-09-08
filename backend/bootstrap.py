"""生产容器一次性引导：数据库迁移 → ES 索引 → 管理员账号。

幂等可重复执行（docker compose 的 bootstrap 服务在每次 up 时运行）。
环境变量：
  ADMIN_EMAIL    默认 admin@reviewlens.dev
  ADMIN_PASSWORD 默认随机生成（打印到本服务日志，请及时修改）
"""
import asyncio
import os
import secrets

from alembic.config import Config

from alembic import command


def _migrate() -> None:
    cfg = Config("alembic.ini")
    print("[bootstrap] 执行数据库迁移 alembic upgrade head ...")
    command.upgrade(cfg, "head")
    print("[bootstrap] 迁移完成。")


async def _es_index() -> None:
    from app.core.es import close_es, ensure_ik_analyzer, ensure_reviews_index

    print("[bootstrap] 初始化 ES 索引（含 IK 分词）...")
    await ensure_ik_analyzer()
    await ensure_reviews_index()
    await close_es()
    print("[bootstrap] ES 索引就绪。")


async def _seed_admin() -> None:
    from sqlalchemy import select

    from app.core.db import AsyncSessionLocal
    from app.core.security import hash_password
    from app.models.user import User, UserRole

    email = os.environ.get("ADMIN_EMAIL", "admin@reviewlens.dev").strip().lower()
    generated = not os.environ.get("ADMIN_PASSWORD")
    password = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(12)

    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(password),
                full_name="系统管理员",
                role=UserRole.ADMIN.value,
            )
            db.add(user)
            action = "created"
        else:
            user.role = UserRole.ADMIN.value
            user.is_active = True
            action = "promoted"
        await db.commit()

    print(f"[bootstrap] 管理员账号已就绪（{action}）：{email}")
    if generated:
        print(f"[bootstrap] 随机管理员密码：{password}  （请立即登录并修改）")


async def _main() -> None:
    _migrate()
    await _es_index()
    await _seed_admin()


if __name__ == "__main__":
    asyncio.run(_main())
    print("[bootstrap] 引导完成。")
