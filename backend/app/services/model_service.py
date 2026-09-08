"""模型管理服务（M6）：发布状态机 + 回滚 + 版本历史 + 审核覆盖率。

职责边界（与 M4 的 analysis_service）：
- analysis_service：训练编排（采样 → 调 NLP 训练 → 记录指标）。
- model_service：模型生命周期管理（发布 / 回滚 / 历史 / 当前生产模型），
  并新增「审核覆盖率」发布门槛和「已审核样本训练」两种能力。

发布状态机：
  evaluation_only --发布(满足门槛)--> published
  published       --新模型发布--> archived（旧模型自动下线）
  published       --回滚--> archived；上一个 archived 恢复为 published
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.prediction import AnalysisRun
from app.models.review import Review
from app.models.review_task import (
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_VERIFIED,
    ReviewTask,
)
from app.services import analysis_service

# 发布门槛（与需求 / M6 一致）
PUBLISH_MACRO_F1 = 0.70
PUBLISH_MIN_TEST_SAMPLES = 1000
PUBLISH_MIN_COVERAGE = 0.80


# ---------- 审核覆盖率 ----------


async def calculate_review_coverage(db: AsyncSession, dataset_version: str) -> float:
    """审核覆盖率 = 已完成审核（非 pending）任务数 / 该数据集审核任务总数。

    当尚未生成审核任务时返回 0.0（无法证明覆盖率达标）。
    """
    total = int(
        (
            await db.execute(
                select(func.count())
                .select_from(ReviewTask)
                .where(ReviewTask.dataset_version == dataset_version)
            )
        ).scalar_one()
    )
    if total == 0:
        return 0.0
    done = int(
        (
            await db.execute(
                select(func.count())
                .select_from(ReviewTask)
                .where(
                    ReviewTask.dataset_version == dataset_version,
                    ReviewTask.status != REVIEW_STATUS_PENDING,
                )
            )
        ).scalar_one()
    )
    return done / total


# ---------- 发布门槛判定 ----------


async def check_publish_criteria(
    db: AsyncSession, run: AnalysisRun
) -> tuple[bool, str]:
    """检查发布全部门槛，返回 (是否可发布, 具体原因/提示)。"""
    if run.status != "succeeded":
        return False, f"仅已成功完成的训练可发布，当前状态：{run.status}"
    if run.macro_f1 is None or run.macro_f1 < PUBLISH_MACRO_F1:
        shown = run.macro_f1 if run.macro_f1 is not None else "None"
        return False, f"Macro-F1（{shown}）未达发布门槛 {PUBLISH_MACRO_F1}"
    if (run.test_samples or 0) < PUBLISH_MIN_TEST_SAMPLES:
        return (
            False,
            f"测试样本（{run.test_samples}）未达门槛 {PUBLISH_MIN_TEST_SAMPLES}",
        )
    coverage = await calculate_review_coverage(db, run.dataset_version)
    if coverage < PUBLISH_MIN_COVERAGE:
        return False, (
            f"审核覆盖率 {coverage:.0%} 未达 {PUBLISH_MIN_COVERAGE:.0%}，"
            "完成更多人工审核后再发布"
        )
    return True, "发布条件满足"


# ---------- 发布状态机 ----------


async def _archive_current_published(
    db: AsyncSession, exclude_run_id: str | None
) -> None:
    """将非当前 run 的已发布模型一律置为 archived（新发布模型生效）。"""
    stmt = select(AnalysisRun).where(AnalysisRun.publish_status == "published")
    if exclude_run_id:
        stmt = stmt.where(AnalysisRun.id != exclude_run_id)
    runs = (await db.execute(stmt)).scalars().all()
    for r in runs:
        r.publish_status = "archived"


async def publish_model(db: AsyncSession, run: AnalysisRun) -> str:
    """发布模型：校验全部门槛 → 下线旧生产模型 → 置当前为 published。"""
    if run.publish_status == "published":
        return "模型已是发布状态"
    ok, reason = await check_publish_criteria(db, run)
    if not ok:
        raise ValueError(reason)
    await _archive_current_published(db, exclude_run_id=run.id)
    run.publish_status = "published"
    await db.commit()
    return "模型已发布"


async def get_current_model(db: AsyncSession) -> AnalysisRun | None:
    """查询当前生产模型（最近成功发布的 published 运行）。"""
    result = await db.execute(
        select(AnalysisRun)
        .where(AnalysisRun.publish_status == "published")
        .order_by(AnalysisRun.created_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def rollback_model(
    db: AsyncSession, run: AnalysisRun | None
) -> AnalysisRun | None:
    """回滚当前生产模型到上一发布版本。

    - 若 run 指明需回滚的运行：把它从 published 置为 archived，
      将存在的最新的一个 archived 模型恢复为 published。
    - 若 run 为空：直接对「当前生产模型」执行回滚。
    返回新生产模型；无上一版本时返回 None。
    """
    current = run or await get_current_model(db)
    if current is None:
        raise ValueError("当前无已发布模型可回滚")
    if current.publish_status != "published":
        raise ValueError("仅可回滚已发布(published)的模型")

    # 取存在的最新的历史版本（archived 中最近一次成功训练者优先）
    result = await db.execute(
        select(AnalysisRun)
        .where(
            AnalysisRun.publish_status == "archived",
            AnalysisRun.id != current.id,
            AnalysisRun.status == "succeeded",
        )
        .order_by(AnalysisRun.created_at.desc())
        .limit(1)
    )
    prev = result.scalars().first()

    current.publish_status = "archived"
    if prev is not None:
        prev.publish_status = "published"
    await db.commit()
    return prev


async def list_model_history(db: AsyncSession) -> list[AnalysisRun]:
    """模型版本历史（按创建时间倒序）。"""
    result = await db.execute(
        select(AnalysisRun).order_by(AnalysisRun.created_at.desc())
    )
    return list(result.scalars().all())


# ---------- 已审核样本训练 ----------


async def sample_reviewed_training_data(
    db: AsyncSession,
    dataset_version: str,
    *,
    cap: int | None = None,
) -> list[dict]:
    """从 approved / verified 人工审核任务采样训练样本（{text,label}）。

    仅使用人工情感（reviewer_sentiment）作为标签，来源限定 approved / verified，
    pending / rejected 不进入训练（满足 M6 验收标准 1）。
    """
    limit = settings.training_sample_cap if cap is None else cap
    per_class = max(limit // 3, 1)

    samples: list[dict] = []
    for label in ("positive", "neutral", "negative"):
        stmt = (
            select(Review.review_text, ReviewTask.reviewer_sentiment)
            .join(
                Review,
                (Review.dataset_version == ReviewTask.dataset_version)
                & (Review.review_id == ReviewTask.review_id),
            )
            .where(
                ReviewTask.dataset_version == dataset_version,
                ReviewTask.status.in_(
                    [REVIEW_STATUS_APPROVED, REVIEW_STATUS_VERIFIED]
                ),
                ReviewTask.reviewer_sentiment == label,
                Review.review_text.isnot(None),
            )
            .limit(per_class)
        )
        rows = (await db.execute(stmt)).all()
        for row in rows:
            text = (row.review_text or "").strip()
            if text:
                samples.append({"text": text, "label": label})
    return samples


async def create_reviewed_run(
    db: AsyncSession,
    *,
    dataset_version: str,
    created_by: str | None,
    algorithm: str = "tfidf_lr",
    min_samples: int | None = None,
) -> AnalysisRun:
    """使用 approved/verified 审核样本触发训练（封装 analysis_service 编排）。"""
    required = settings.min_training_samples if min_samples is None else min_samples
    samples = await sample_reviewed_training_data(db, dataset_version)
    if len(samples) < required:
        raise ValueError(
            f"已审核训练样本不足：{len(samples)} < {required}。"
            "请先生成并完成足够的人工审核，或改用弱标签训练。"
        )
    return await analysis_service.create_run_with_samples(
        db,
        dataset_version=dataset_version,
        samples=samples,
        created_by=created_by,
        algorithm=algorithm,
    )
