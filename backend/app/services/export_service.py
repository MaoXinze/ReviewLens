"""导出服务（M9）。

职责：
- export_reviews：按数据集/筛选条件查询评论，生成 CSV（含评论原文 + 当前模型预测
  结果 + 人工审核标签），上传 MinIO 并写入 export_records（验收标准 5、6）。
- list_exports：导出记录分页。
- get_export_record / download_bytes：下载文件（从 MinIO 读取字节）。

预测结果取当前生产模型（published）的 review_predictions；未发布模型时预测列为空。
审核标签取 review_tasks 中已审核（approved/verified）的人工情感。
"""
import csv
from io import StringIO
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.minio import read_bytes, upload_bytes
from app.models.alert import ExportRecord
from app.models.prediction import ReviewPrediction
from app.models.review import Review
from app.models.review_task import (
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_VERIFIED,
    ReviewTask,
)
from app.services import model_service

CSV_HEADERS = [
    "review_id",
    "product_id",
    "rating",
    "reviewed_at",
    "review_text",
    "predicted_sentiment",
    "confidence",
    "reviewer_sentiment",
]


def _filters_dict(req) -> dict:
    return {
        "product_id": req.product_id,
        "sentiment": req.sentiment,
        "rating_min": req.rating_min,
        "rating_max": req.rating_max,
    }


async def _query_rows(
    db: AsyncSession,
    *,
    dataset_version: str,
    product_id: str | None,
    sentiment: str | None,
    rating_min: int | None,
    rating_max: int | None,
    model_version: str | None,
):
    pred_cond = (ReviewPrediction.dataset_version == Review.dataset_version) & (
        ReviewPrediction.review_id == Review.review_id
    )
    if model_version:
        pred_cond = pred_cond & (
            ReviewPrediction.model_version == model_version
        )
    else:
        pred_cond = pred_cond & sa.false()

    stmt = (
        select(
            Review.review_id,
            Review.product_id,
            Review.rating,
            Review.reviewed_at,
            Review.review_text,
            ReviewPrediction.overall_sentiment.label("pred_sentiment"),
            ReviewPrediction.confidence.label("confidence"),
            ReviewTask.reviewer_sentiment,
        )
        .where(Review.dataset_version == dataset_version)
        .outerjoin(ReviewPrediction, pred_cond)
        .outerjoin(
            ReviewTask,
            (ReviewTask.dataset_version == Review.dataset_version)
            & (ReviewTask.review_id == Review.review_id)
            & (ReviewTask.status.in_([REVIEW_STATUS_APPROVED, REVIEW_STATUS_VERIFIED])),
        )
    )
    if product_id:
        stmt = stmt.where(Review.product_id == product_id)
    if sentiment:
        stmt = stmt.where(ReviewPrediction.overall_sentiment == sentiment)
    if rating_min is not None:
        stmt = stmt.where(Review.rating >= rating_min)
    if rating_max is not None:
        stmt = stmt.where(Review.rating <= rating_max)
    return (await db.execute(stmt)).all()


def build_csv(rows) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADERS)
    for r in rows:
        writer.writerow(
            [
                r.review_id,
                r.product_id,
                r.rating,
                r.reviewed_at.strftime("%Y-%m-%d %H:%M:%S")
                if r.reviewed_at
                else "",
                r.review_text or "",
                r.pred_sentiment or "",
                "" if r.confidence is None else r.confidence,
                r.reviewer_sentiment or "",
            ]
        )
    return buffer.getvalue()


async def export_reviews(
    db: AsyncSession, *, req, user_id: str
) -> ExportRecord:
    """执行导出：查询 → CSV → MinIO → 记录。"""
    current = await model_service.get_current_model(db)
    model_version = current.model_version if current else None
    rows = await _query_rows(
        db,
        dataset_version=req.dataset_version,
        product_id=req.product_id,
        sentiment=req.sentiment,
        rating_min=req.rating_min,
        rating_max=req.rating_max,
        model_version=model_version,
    )
    csv_content = build_csv(rows)
    object_name = f"exports/{user_id}/{uuid4().hex}.csv"
    await upload_bytes(object_name, csv_content.encode("utf-8-sig"))

    record = ExportRecord(
        id=str(uuid4()),
        exported_by=user_id,
        dataset_version=req.dataset_version,
        filters=_filters_dict(req),
        file_path=object_name,
        row_count=len(rows),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def list_exports(
    db: AsyncSession, *, page: int = 1, page_size: int = 20
) -> tuple[list[ExportRecord], int]:
    total = (
        await db.execute(select(func.count()).select_from(ExportRecord))
    ).scalar_one()
    result = await db.execute(
        select(ExportRecord)
        .order_by(ExportRecord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), int(total)


async def get_export_record(db: AsyncSession, export_id: str) -> ExportRecord | None:
    return await db.get(ExportRecord, export_id)


async def download_bytes(record: ExportRecord) -> bytes:
    """从 MinIO 读取导出文件字节。"""
    return await read_bytes(record.file_path)
