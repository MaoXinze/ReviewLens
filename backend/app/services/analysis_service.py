"""训练运行编排服务（M4）：采样弱标签 → 调 NLP 训练 → 记录到 analysis_runs。

P2 基线使用「评分 → 情感」弱标签采样
（rating>=4=>positive, ==3=>neutral, <=2=>negative）。
待 M5 落地后可将样本来源替换为 approved/verified 人工审核标签
（同接口返回 {text,label}）。
"""
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.prediction import AnalysisRun
from app.models.review import Review
from app.services import nlp_client

# 发布门槛（与需求/M6 一致）
PUBLISH_MACRO_F1 = 0.70
PUBLISH_MIN_TEST_SAMPLES = 1000


def rating_to_sentiment(rating: int) -> str:
    """评分 → 弱情感标签。"""
    if rating >= 4:
        return "positive"
    if rating == 3:
        return "neutral"
    return "negative"


async def sample_training_data(
    db: AsyncSession,
    dataset_version: str,
    *,
    cap: int | None = None,
) -> list[dict]:
    """按类别均衡采样评论文本作为训练样本（{text,label}），最多 cap 条。"""
    limit = settings.training_sample_cap if cap is None else cap
    per_class = max(limit // 3, 1)

    def class_stmt(rating_min: int, rating_max: int):
        return (
            select(Review.review_text, Review.rating)
            .where(
                Review.dataset_version == dataset_version,
                Review.rating.isnot(None),
                Review.rating >= rating_min,
                Review.rating <= rating_max,
            )
            .limit(per_class)
        )

    samples: list[dict] = []
    for rating_min, rating_max in ((4, 5), (3, 3), (1, 2)):
        rows = (await db.execute(class_stmt(rating_min, rating_max))).all()
        label = rating_to_sentiment(rating_max)
        for row in rows:
            text = (row.review_text or "").strip()
            if text:
                samples.append({"text": text, "label": label})
    return samples


async def create_run(
    db: AsyncSession,
    *,
    dataset_version: str,
    created_by: str | None,
    algorithm: str = "tfidf_lr",
    min_samples: int | None = None,
) -> AnalysisRun:
    """采样弱标签 → 调用 NLP 训练 → 回写 analysis_runs。"""
    required = settings.min_training_samples if min_samples is None else min_samples
    samples = await sample_training_data(db, dataset_version)
    if len(samples) < required:
        raise ValueError(
            f"训练样本不足：{len(samples)} < {required}。"
            "请先导入足够且带评分的评论数据。"
        )
    return await create_run_with_samples(
        db,
        dataset_version=dataset_version,
        samples=samples,
        created_by=created_by,
        algorithm=algorithm,
    )


async def create_run_with_samples(
    db: AsyncSession,
    *,
    dataset_version: str,
    samples: list[dict],
    created_by: str | None,
    algorithm: str = "tfidf_lr",
) -> AnalysisRun:
    """用给定的样本列表调用 NLP 训练并回写 analysis_runs（M6 reviewed 训练复用）。"""
    now = datetime.now(UTC)
    run = AnalysisRun(
        id=str(uuid4()),
        dataset_version=dataset_version,
        model_version="",  # 训练成功后回填
        algorithm=algorithm,
        random_seed=settings.default_random_seed,
        status="running",
        started_at=now,
        created_by=created_by,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    try:
        record = await nlp_client.train_model(
            samples, test_size=settings.default_test_size, random_seed=run.random_seed
        )
        run.model_version = record["model_version"]
        run.train_samples = record.get("train_samples", len(samples))
        run.test_samples = record.get("test_samples", 0)
        run.macro_f1 = record.get("macro_f1")
        run.accuracy = record.get("accuracy")
        run.classification_report = record.get("classification_report")
        run.confusion_matrix = record.get("confusion_matrix")
        run.status = "succeeded"
        run.publish_status = record.get("publish_status", "evaluation_only")
        run.finished_at = datetime.now(UTC)
    except (nlp_client.NLPUnavailable, nlp_client.NLPRemoteError) as exc:
        run.status = "failed"
        run.error_message = str(exc)[:1000]
        run.finished_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(run)
    return run


async def list_runs(
    db: AsyncSession,
    *,
    dataset_version: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[AnalysisRun], int]:
    stmt = select(AnalysisRun)
    count_stmt = select(func.count()).select_from(AnalysisRun)
    if dataset_version:
        stmt = stmt.where(AnalysisRun.dataset_version == dataset_version)
        count_stmt = count_stmt.where(AnalysisRun.dataset_version == dataset_version)
    total = (await db.execute(count_stmt)).scalar_one()
    result = await db.execute(
        stmt.order_by(AnalysisRun.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), int(total)


async def get_run(db: AsyncSession, run_id: str) -> AnalysisRun | None:
    return await db.get(AnalysisRun, run_id)


async def publish_run(db: AsyncSession, run: AnalysisRun) -> str:
    """发布模型：需先成功训练且满足发布门槛；返回消息。"""
    if run.status != "succeeded":
        raise ValueError("仅已成功完成的训练可发布")
    if run.publish_status == "published":
        return "模型已是发布状态"
    if run.macro_f1 is None or run.macro_f1 < PUBLISH_MACRO_F1:
        raise ValueError(f"Macro-F1（{run.macro_f1}）未达发布门槛 {PUBLISH_MACRO_F1}")
    if (run.test_samples or 0) < PUBLISH_MIN_TEST_SAMPLES:
        raise ValueError(
            f"测试样本（{run.test_samples}）未达发布门槛 {PUBLISH_MIN_TEST_SAMPLES}"
        )
    run.publish_status = "published"
    await db.commit()
    return "模型已发布"
