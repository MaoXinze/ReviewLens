"""ARQ 批量推理任务：读 PG → 调 NLP 推理 → 写 review_predictions → 回写 ES。

作为 worker 的独立函数运行（见 app/worker.py）。任何异常都会记录失败并抛出，
由 ARQ 将任务标记失败；不静默吞错。
"""
from uuid import uuid4

from sqlalchemy import select

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.es import update_review_predictions
from app.models.prediction import ReviewPrediction
from app.models.review import Review
from app.services import nlp_client


def _to_orm(p: dict, dataset_version: str, model_version: str) -> ReviewPrediction:
    return ReviewPrediction(
        id=str(uuid4()),
        dataset_version=dataset_version,
        review_id=p["review_id"],
        model_version=model_version,
        overall_sentiment=p["overall_sentiment"],
        confidence=float(p.get("confidence", 0.0)),
        aspects=p.get("aspects", []),
    )


async def run_inference(
    ctx, dataset_version: str, model_version: str | None = None
) -> dict:
    """推理任务主体。ctx 为 ARQ worker 上下文（未使用）。

    每批独立 commit：ORM 对象不全程驻留内存，且已提交批次的 PG 与
    ES 状态保持一致（ES 更新在 commit 之后）。
    """
    inferred_total = 0
    async with AsyncSessionLocal() as db:
        offset = 0
        while True:
            result = await db.execute(
                select(Review.review_id, Review.review_text)
                .where(Review.dataset_version == dataset_version)
                .order_by(Review.reviewed_at)
                .offset(offset)
                .limit(settings.inference_batch_size)
            )
            rows = result.all()
            if not rows:
                break

            input_reviews = [
                {"review_id": rid, "text": text} for rid, text in rows
            ]
            predictions = await nlp_client.infer_batch(input_reviews, model_version)
            resolved_model = (
                predictions[0].get("model_version") if predictions else model_version
            ) or model_version or "unknown"

            batch: list[ReviewPrediction] = []
            for pred in predictions:
                if pred.get("overall_sentiment") is None:
                    continue
                batch.append(_to_orm(pred, dataset_version, resolved_model))
            if batch:
                db.add_all(batch)
                await db.commit()
                await update_review_predictions(
                    dataset_version, predictions, resolved_model
                )

            inferred_total += len(predictions)
            offset += settings.inference_batch_size

    return {
        "status": "completed",
        "dataset_version": dataset_version,
        "inferred": inferred_total,
    }
