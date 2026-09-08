"""ReviewLens 后端入口（FastAPI 应用）。

业务路由由各模块挂载。M1 认证/用户管理，M2 数据集导入。
退出时关闭 ES 客户端连接。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    alerts,
    analysis_runs,
    auth,
    datasets,
    exports,
    insights,
    issues,
    predictions,
    review_tasks,
    reviews,
    users,
)
from app.core.config import settings
from app.core.es import close_es


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_security()
    try:
        yield
    finally:
        await close_es()


app = FastAPI(
    title="ReviewLens API",
    description="面向电商品牌的商品评论体验分析平台",
    version="0.3.0",
    lifespan=lifespan,
)

# CORS 白名单（显式枚举，不使用正则通配）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(datasets.router)
app.include_router(reviews.router)
app.include_router(predictions.router)
app.include_router(analysis_runs.router)
app.include_router(review_tasks.router)
app.include_router(insights.router)
app.include_router(issues.router)
app.include_router(alerts.router)
app.include_router(alerts.alerts_router)
app.include_router(exports.router)


@app.get("/health", tags=["system"])
async def health() -> dict:
    """存活检查（Liveness）。"""
    return {"status": "ok", "service": "reviewlens-backend"}
