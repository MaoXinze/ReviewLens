"""预测服务：批量推理编排 + 预测查询（M4）。

- submit_batch_inference: 校验数据集存在 → 入队 ARQ run_inference 任务
- list_predictions / list_low_confidence: 结果查询（供前端与 M5 审核取数）
"""
from arq.connections import RedisSettings, create_pool
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.dataset import Dataset
from app.models.prediction import ReviewPrediction


async def enqueue_inference(dataset_version: str, model_version: str | None) -> None:
    """将批量推理任务入队（ARQ Redis 队列）。"""
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await redis.enqueue_job("run_inference", dataset_version, model_version)
    finally:
        await redis.aclose()


async def submit_batch_inference(
    db: AsyncSession, dataset_version: str, model_version: str | None = None
) -> dict:
    """校验数据集存在后提交推理任务。"""
    dataset = (
        await db.execute(
            select(Dataset).where(Dataset.dataset_version == dataset_version)
        )
    ).scalar_one_or_none()
    if dataset is None:
        raise ValueError("数据集不存在")
    if dataset.status != "completed":
        raise ValueError("数据集尚未导入完成，无法推理")

    job_id = await enqueue_inference(dataset_version, model_version)
    return {
        "job_id": str(job_id) if job_id else None,
        "dataset_version": dataset_version,
        "model_version": model_version,
    }


async def list_predictions(
    db: AsyncSession,
    *,
    dataset_version: str | None = None,
    model_version: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ReviewPrediction], int]:
    stmt = select(ReviewPrediction)
    count_stmt = select(func.count()).select_from(ReviewPrediction)
    if dataset_version:
        stmt = stmt.where(ReviewPrediction.dataset_version == dataset_version)
        count_stmt = count_stmt.where(
            ReviewPrediction.dataset_version == dataset_version
        )
    if model_version:
        stmt = stmt.where(ReviewPrediction.model_version == model_version)
        count_stmt = count_stmt.where(ReviewPrediction.model_version == model_version)

    total = (await db.execute(count_stmt)).scalar_one()
    result = await db.execute(
        stmt.order_by(ReviewPrediction.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), int(total)


async def list_low_confidence(
    db: AsyncSession,
    *,
    dataset_version: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ReviewPrediction], int]:
    """置信度低于阈值的预测列表（供 M5 审核）。"""
    stmt = select(ReviewPrediction).where(
        ReviewPrediction.confidence < settings.low_confidence_threshold
    )
    count_stmt = select(func.count()).select_from(ReviewPrediction).where(
        ReviewPrediction.confidence < settings.low_confidence_threshold
    )
    if dataset_version:
        stmt = stmt.where(ReviewPrediction.dataset_version == dataset_version)
        count_stmt = count_stmt.where(
            ReviewPrediction.dataset_version == dataset_version
        )
    total = (await db.execute(count_stmt)).scalar_one()
    result = await db.execute(
        stmt.order_by(ReviewPrediction.confidence.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), int(total)
