"""人工审核工作流服务（M5）。

职责：
- generate_tasks：从 review_predictions 按抽样组抽取待审核任务
  （优先级 low_confidence → high_risk → random）。
- 连续审核：get_next_task 按 status=pending 顺序取一条。
- 状态机：pending --运营提交--> approved/rejected；
  approved --二次复核--> verified/rejected。
- 审核历史：任何字段变更写入 review_task_history（谁/何时/改了什么/为什么）。
- summary：总任务数、完成率、一致率。
"""
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.prediction import ReviewPrediction
from app.models.review import Review
from app.models.review_task import (
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_REJECTED,
    REVIEW_STATUS_VERIFIED,
    SAMPLE_GROUP_HIGH_RISK,
    SAMPLE_GROUP_LOW_CONFIDENCE,
    SAMPLE_GROUP_RANDOM,
    ReviewTask,
    ReviewTaskHistory,
)
from app.models.user import User


def _json(value) -> str | None:
    """历史对象值转字符串；None 保持 None。"""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _sampling_group_of(pred: ReviewPrediction) -> tuple[str, str]:
    """依据模型上下文给预测分派采样组与原因。"""
    if pred.confidence < settings.low_confidence_threshold:
        conf = f"{pred.confidence:.2f}"
        threshold = settings.low_confidence_threshold
        return (
            SAMPLE_GROUP_LOW_CONFIDENCE,
            f"系统置信度 {conf} 低于 {threshold}，需人工确认",
        )
    if pred.overall_sentiment == "negative":
        return SAMPLE_GROUP_HIGH_RISK, "预测为差评，需运营重点关注并确认属性归因"
    return SAMPLE_GROUP_RANDOM, "随机抽样复核系统预测"


async def generate_tasks(
    db: AsyncSession,
    *,
    dataset_version: str,
    model_version: str | None,
    count: int,
) -> dict:
    """从预测结果抽取 count 条审核任务；已存在同 (dataset_version, review_id) 的跳过。

    返回值：{"created": int, "skipped": int}。
    """
    if count < 1:
        raise ValueError("生成数量至少为 1")

    stmt = select(ReviewPrediction).where(
        ReviewPrediction.dataset_version == dataset_version
    )
    if model_version:
        stmt = stmt.where(ReviewPrediction.model_version == model_version)
    predictions = list((await db.execute(stmt)).scalars().all())
    if not predictions:
        raise ValueError("未找到该数据集的预测结果，请先运行批量推理")

    # 按采样优先级排序：低置信度优先，其次高风险差评，最后随机
    def _rank(pred: ReviewPrediction) -> tuple[int, float]:
        if pred.confidence < settings.low_confidence_threshold:
            return (0, pred.confidence)
        if pred.overall_sentiment == "negative":
            return (1, -1.0)
        return (2, 1.0)

    predictions.sort(key=_rank)

    # 排除已存在的任务，保证 (dataset_version, review_id) 唯一
    existing_ids = set(
        (
            await db.execute(
                select(ReviewTask.review_id).where(
                    ReviewTask.dataset_version == dataset_version
                )
            )
        ).scalars().all()
    )

    created = 0
    skipped = 0
    now = datetime.now(UTC)
    for pred in predictions:
        if created >= count:
            break
        if pred.review_id in existing_ids:
            skipped += 1
            continue
        group, reason = _sampling_group_of(pred)
        existing_ids.add(pred.review_id)
        db.add(
            ReviewTask(
                id=str(uuid4()),
                dataset_version=pred.dataset_version,
                review_id=pred.review_id,
                sampling_group=group,
                sampling_reason=reason,
                system_sentiment=pred.overall_sentiment,
                system_confidence=pred.confidence,
                system_aspects=pred.aspects or [],
                model_version=pred.model_version,
                status=REVIEW_STATUS_PENDING,
                created_at=now,
            )
        )
        created += 1

    await db.commit()
    return {"created": created, "skipped": skipped}


async def list_tasks(
    db: AsyncSession,
    *,
    status: str | None = None,
    sampling_group: str | None = None,
    dataset_version: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ReviewTask], int]:
    stmt = select(ReviewTask)
    count_stmt = select(func.count()).select_from(ReviewTask)
    if status:
        stmt = stmt.where(ReviewTask.status == status)
        count_stmt = count_stmt.where(ReviewTask.status == status)
    if sampling_group:
        stmt = stmt.where(ReviewTask.sampling_group == sampling_group)
        count_stmt = count_stmt.where(ReviewTask.sampling_group == sampling_group)
    if dataset_version:
        stmt = stmt.where(ReviewTask.dataset_version == dataset_version)
        count_stmt = count_stmt.where(
            ReviewTask.dataset_version == dataset_version
        )
    total = (await db.execute(count_stmt)).scalar_one()
    result = await db.execute(
        stmt.order_by(ReviewTask.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), int(total)


async def get_task(db: AsyncSession, task_id: str) -> ReviewTask | None:
    return await db.get(ReviewTask, task_id)


async def get_review_quote(
    db: AsyncSession, task: ReviewTask
) -> Review | None:
    """按 (dataset_version, review_id) 取原始评论供审核判断。"""
    result = await db.execute(
        select(Review).where(
            Review.dataset_version == task.dataset_version,
            Review.review_id == task.review_id,
        ).limit(1)
    )
    return result.scalars().first()


async def get_next_task(
    db: AsyncSession, *, dataset_version: str | None = None
) -> ReviewTask | None:
    """取下一条待审核任务（连续审核）。"""
    stmt = select(ReviewTask).where(ReviewTask.status == REVIEW_STATUS_PENDING)
    if dataset_version:
        stmt = stmt.where(ReviewTask.dataset_version == dataset_version)
    stmt = stmt.order_by(ReviewTask.created_at.asc()).limit(1)
    result = await db.execute(stmt)
    return result.scalars().first()


async def _record_change(
    db: AsyncSession,
    *,
    task_id: str,
    field_name: str,
    old_value: str | None,
    new_value: str | None,
    changed_by: str | None,
    reason: str | None,
    changed_at: datetime | None = None,
) -> None:
    if old_value == new_value:
        return
    db.add(
        ReviewTaskHistory(
            id=str(uuid4()),
            task_id=task_id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            changed_by=changed_by,
            changed_at=changed_at or datetime.now(UTC),
            reason=reason,
        )
    )


async def submit_review(
    db: AsyncSession,
    task: ReviewTask,
    reviewer: User,
    *,
    status: str,
    reviewer_sentiment: str | None,
    reviewer_aspects: list[dict] | None,
    review_reason: str,
    review_note: str | None,
) -> ReviewTask:
    """运营提交审核结果：pending → approved/rejected。"""
    if task.status != REVIEW_STATUS_PENDING:
        raise ValueError(f"仅待审核(pending)任务可提交，当前状态：{task.status}")
    if status not in (REVIEW_STATUS_APPROVED, REVIEW_STATUS_REJECTED):
        raise ValueError(f"非法审核结果：{status}")

    now = datetime.now(UTC)
    await _record_change(
        db, task_id=task.id, field_name="status", old_value=task.status,
        new_value=status, changed_by=reviewer.id, reason=review_reason,
    )
    if reviewer_sentiment != task.reviewer_sentiment:
        await _record_change(
            db, task_id=task.id, field_name="reviewer_sentiment",
            old_value=task.reviewer_sentiment, new_value=reviewer_sentiment,
            changed_by=reviewer.id, reason=review_reason,
        )
    if _json(reviewer_aspects) != _json(task.reviewer_aspects):
        await _record_change(
            db, task_id=task.id, field_name="reviewer_aspects",
            old_value=_json(task.reviewer_aspects), new_value=_json(reviewer_aspects),
            changed_by=reviewer.id, reason=review_reason,
        )
    if review_reason != task.review_reason:
        await _record_change(
            db, task_id=task.id, field_name="review_reason",
            old_value=task.review_reason, new_value=review_reason,
            changed_by=reviewer.id, reason=review_reason,
        )
    if review_note != task.review_note:
        await _record_change(
            db, task_id=task.id, field_name="review_note",
            old_value=task.review_note, new_value=review_note,
            changed_by=reviewer.id, reason=review_reason,
        )

    task.status = status
    task.reviewer_sentiment = reviewer_sentiment
    task.reviewer_aspects = reviewer_aspects or []
    task.review_reason = review_reason
    task.review_note = review_note
    task.reviewer_id = reviewer.id
    task.reviewed_at = now
    await db.commit()
    await db.refresh(task)
    return task


async def second_review(
    db: AsyncSession,
    task: ReviewTask,
    reviewer: User,
    *,
    status: str,
    review_note: str | None,
) -> ReviewTask:
    """二次复核：approved → verified/rejected。

    入参 status 采用审核语义二值 approved/rejected：
    - approved  → 通过二次复核（verified）
    - rejected  → 否决运营审批（rejected）
    """
    if task.status != REVIEW_STATUS_APPROVED:
        raise ValueError(f"仅已审批(approved)任务可二次复核，当前状态：{task.status}")
    if status not in (REVIEW_STATUS_APPROVED, REVIEW_STATUS_REJECTED):
        raise ValueError(f"非法复核结果：{status}")

    target = (REVIEW_STATUS_VERIFIED if status == REVIEW_STATUS_APPROVED else status)
    now = datetime.now(UTC)
    await _record_change(
        db, task_id=task.id, field_name="status", old_value=task.status,
        new_value=target, changed_by=reviewer.id, reason=status,
    )
    if review_note != task.review_note:
        await _record_change(
            db, task_id=task.id, field_name="review_note",
            old_value=task.review_note, new_value=review_note,
            changed_by=reviewer.id, reason=status,
        )

    task.status = target
    if review_note:
        task.review_note = review_note
    task.second_reviewer_id = reviewer.id
    task.second_reviewed_at = now
    await db.commit()
    await db.refresh(task)
    return task


async def summary(
    db: AsyncSession, *, dataset_version: str | None = None
) -> dict:
    """审核进度统计：总任务数、完成率、一致率。"""
    base = select(ReviewTask).where(ReviewTask.status.is_not(None))
    if dataset_version:
        base = base.where(ReviewTask.dataset_version == dataset_version)

    async def _count(*clauses) -> int:
        stmt = select(func.count()).select_from(ReviewTask)
        if dataset_version:
            stmt = stmt.where(ReviewTask.dataset_version == dataset_version)
        stmt = stmt.where(*clauses)
        return int((await db.execute(stmt)).scalar_one())

    total = await _count()
    done = await _count(ReviewTask.status != REVIEW_STATUS_PENDING)
    pending = await _count(ReviewTask.status == REVIEW_STATUS_PENDING)
    approved = await _count(ReviewTask.status == REVIEW_STATUS_APPROVED)
    verified = await _count(ReviewTask.status == REVIEW_STATUS_VERIFIED)
    rejected = await _count(ReviewTask.status == REVIEW_STATUS_REJECTED)

    # 一致率：已审核且给出人工情感的任务中，与系统预测情感一致的比例
    agreement_denom = await _count(
        ReviewTask.status != REVIEW_STATUS_PENDING,
        ReviewTask.reviewer_sentiment.is_not(None),
        ReviewTask.system_sentiment.is_not(None),
    )
    agreement_hit = await _count(
        ReviewTask.status != REVIEW_STATUS_PENDING,
        ReviewTask.reviewer_sentiment.is_not(None),
        ReviewTask.system_sentiment.is_not(None),
        ReviewTask.reviewer_sentiment == ReviewTask.system_sentiment,
    )
    agreement_rate = (agreement_hit / agreement_denom) if agreement_denom else 0.0
    completion_rate = (done / total) if total else 0.0

    return {
        "dataset_version": dataset_version,
        "total": total,
        "done": done,
        "pending": pending,
        "approved": approved,
        "verified": verified,
        "rejected": rejected,
        "completion_rate": round(completion_rate, 4),
        "agreement_rate": round(agreement_rate, 4),
    }
