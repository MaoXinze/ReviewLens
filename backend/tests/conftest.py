"""pytest 共享夹具。

测试使用独立数据库（默认 `reviewlens_test`，可用 TEST_DATABASE_URL 覆盖，供 CI 用）。
通过 Base.metadata 建表/删表，并 override 应用的 get_db 依赖，避免污染开发库。
M2 之后建表需额外创建 reviews 的 DEFAULT 分区。
"""
import os

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# 关键：让 config 在首次读取时带上测试密钥
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_at_least_16_chars")

from app.core import config  # noqa: E402
from app.core.db import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import Base  # noqa: E402

TEST_SECRET = "test_secret_key_at_least_16_chars"
config.get_settings.cache_clear()
os.environ["JWT_SECRET_KEY"] = TEST_SECRET
if not os.environ.get("TEST_DATABASE_URL"):
    os.environ["TEST_DATABASE_URL"] = (
        "postgresql+asyncpg://reviewlens:reviewlens_dev_only@localhost:15432/reviewlens_test"
    )

TEST_DB_URL = os.environ["TEST_DATABASE_URL"]

# 分区默认表：承接未命中具体分区的新行
_CREATE_DEFAULT_PARTITION = """
CREATE TABLE IF NOT EXISTS reviews_default PARTITION OF reviews DEFAULT
"""


@pytest.fixture(autouse=True)
def _reset_auth_limiters():
    """每个测试前清空进程内限流状态，避免跨测试累积触发 429。"""
    from app.api.v1 import auth

    auth.account_limiter.clear()
    auth.ip_limiter.clear()
    auth.register_limiter.clear()
    yield


@pytest_asyncio.fixture
async def client():
    """为每个测试提供独立的表空间与 ASGI 客户端。"""
    engine = create_async_engine(TEST_DB_URL, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(sa.text(_CREATE_DEFAULT_PARTITION))

    async def override_get_db():
        async with SessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
    await engine.dispose()
