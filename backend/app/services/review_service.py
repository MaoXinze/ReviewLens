"""评论查询逻辑（M2：数据集内评论列表）。

M3 搜索引擎上线后，全库搜索将走 ES；本模块仅负责按数据集查询。
"""
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset
from app.models.review import Review


async def list_products(
    db: AsyncSession, *, version: str, limit: int = 50
) -> list[dict]:
    """数据集内评论量最高的商品（SKU）列表，供 SKU 对比选择。"""
    rows = (
        await db.execute(
            select(Review.product_id, func.count().label("review_count"))
            .where(Review.dataset_version == version)
            .group_by(Review.product_id)
            .order_by(desc("review_count"))
            .limit(limit)
        )
    ).all()
    return [
        {"product_id": r.product_id, "review_count": r.review_count} for r in rows
    ]


async def list_datasets(
    db: AsyncSession, *, page: int, page_size: int
) -> tuple[list[Dataset], int]:
    total = (
        await db.execute(select(func.count()).select_from(Dataset))
    ).scalar_one()
    result = await db.execute(
        select(Dataset)
        .order_by(Dataset.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), int(total)


async def get_dataset(db: AsyncSession, version: str) -> Dataset | None:
    return (
        await db.execute(select(Dataset).where(Dataset.dataset_version == version))
    ).scalar_one_or_none()


async def list_reviews(
    db: AsyncSession, *, version: str, page: int, page_size: int
) -> tuple[list[Review], int]:
    total = (
        await db.execute(
            select(func.count())
            .select_from(Review)
            .where(Review.dataset_version == version)
        )
    ).scalar_one()
    result = await db.execute(
        select(Review)
        .where(Review.dataset_version == version)
        .order_by(Review.reviewed_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), int(total)
