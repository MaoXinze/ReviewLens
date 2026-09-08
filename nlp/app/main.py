"""ReviewLens NLP 服务入口（FastAPI 应用）。

独立于后端运行的 Python 服务（端口 8100），由 backend 通过 HTTP 调用。
提供健康检查 + M4 推理/训练/评测路由。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_dirs()
    yield


app = FastAPI(
    title="ReviewLens NLP Service",
    description="文本预处理 / 属性抽取 / 情感分类 / 模型训练与评测",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health", tags=["system"])
async def health() -> dict:
    """存活检查。"""
    return {"status": "ok", "service": "reviewlens-nlp"}