"""问题卡管理服务（M8）。

职责：
- create_issue：从看板洞察创建问题卡，校验来源评论归属数据集。
- 状态机：open → in_progress → pending_validation → closed，
  支持 open/in_progress、in_progress/pending_validation 双向退回，
  closed 为终态不可流转（满足验收标准 1、5）。
- 审计轨迹：任何字段变更（status/severity/assignee/resolution_note/
  validation_note）写入 issue_history（谁/何时/改了什么，验收标准 3）。
- retrospect：关闭后的效果回测，对比创建前后该属性的差评率（验收标准 4）。

差评率基于 review_predictions（PG，NLP 预测结果，与 M6/M7 同源口径）聚合，
通过 review_id 关联 reviews 获取 reviewed_at / product_id 用于过滤；不再依赖 ES。
"""
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset
from app.models.issue import (
    ISSUE_STATUS_CLOSED,
    ISSUE_STATUS_IN_PROGRESS,
    ISSUE_STATUS_OPEN,
    ISSUE_STATUS_PENDING_VALIDATION,
    ISSUE_TRANSITIONS,
    Issue,
    IssueHistory,
)
from app.models.review import Review
from app.models.user import User

_NEGATIVE = "negative"


def _json(value) -> str | None:
    """历史对象值转字符串；None 保持 None。"""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


# ---------- 差评率聚合（基于 PG review_predictions，与 M6/M7 同源） ----------

# JSONB 包含匹配需用数组包裹的单元素模式（aspects 为 [{aspect,sentiment,...},...]）。
def _aspect_pattern(aspect: str, *, negative: bool = False) -> str:
    obj = {"aspect": aspect}
    if negative:
        obj["sentiment"] = _NEGATIVE
    return json.dumps([obj], ensure_ascii=False)


async def _aspect_negative_rate(
    db: AsyncSession, *, dataset_version: str, aspect: str,
    product_id: str | None = None, end_date: datetime | None = None,
    start_date: datetime | None = None,
) -> float:
    """计算给定数据集/属性维度下的差评率（0~1），支持时间窗口过滤。

    数据源为 review_predictions（PG 预测结果），通过 review_id 关联 reviews
    获取 reviewed_at / product_id 用于过滤；按 review_id 去重，避免多模型叠加膨胀。

    - end_date：仅统计该时间点（含）之前的评论。
    - start_date：仅统计该时间点（含）之后的评论。
    """
    conds = ["rp.dataset_version = :dv"]
    params: dict = {"dv": dataset_version}
    if product_id:
        conds.append("rv.product_id = :pid")
        params["pid"] = product_id
    if end_date is not None:
        conds.append("rv.reviewed_at <= :end_date")
        params["end_date"] = end_date
    if start_date is not None:
        conds.append("rv.reviewed_at >= :start_date")
        params["start_date"] = start_date

    sql = text(
        f"""
        SELECT
          count(DISTINCT rp.review_id) FILTER (
              WHERE rp.aspects @> CAST(:neg AS jsonb))::float
          / NULLIF(
              count(DISTINCT rp.review_id) FILTER (
              WHERE rp.aspects @> CAST(:asp AS jsonb))::float, 0) AS rate
        FROM review_predictions rp
        JOIN reviews rv
          ON rv.dataset_version = rp.dataset_version
         AND rv.review_id = rp.review_id
        WHERE {" AND ".join(conds)}
        """
    )
    params["asp"] = _aspect_pattern(aspect)
    params["neg"] = _aspect_pattern(aspect, negative=True)
    result = (await db.execute(sql, params)).scalar_one()
    return round(float(result), 4) if result is not None else 0.0


async def get_latest_dataset(db: AsyncSession) -> Dataset | None:
    """最近一次成功导入的数据集（按创建时间倒序）。"""
    stmt = (
        select(Dataset)
        .where(Dataset.status == "completed")
        .order_by(Dataset.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


# ---------- 问题卡增删查改 ----------


async def create_issue(
    db: AsyncSession, *, req, creator: User, assignee: User | None = None
) -> Issue:
    """创建问题卡；校验数据集存在、来源评论归属该数据集。"""
    dataset_exists = (
        await db.execute(
            select(Dataset.dataset_version).where(
                Dataset.dataset_version == req.dataset_version
            )
        )
    ).scalar_one_or_none()
    if dataset_exists is None:
        raise ValueError("数据集不存在")

    # 去重后校验每条来源评论必须属于该数据集（验收标准 2）
    source_ids = list(dict.fromkeys(req.source_review_ids))
    if source_ids:
        rows = (
            await db.execute(
                select(Review.review_id).where(
                    Review.dataset_version == req.dataset_version,
                    Review.review_id.in_(source_ids),
                )
            )
        ).scalars().all()
        if len(rows) != len(source_ids):
            raise ValueError("来源评论必须全部属于该数据集")
    else:
        raise ValueError("至少需要 1 条来源评论作为证据")

    issue = Issue(
        id=str(uuid4()),
        dataset_version=req.dataset_version,
        title=req.title,
        aspect=req.aspect,
        severity=req.severity,
        status=ISSUE_STATUS_OPEN,
        description=req.description,
        source_review_ids=source_ids,
        assignee=assignee.id if assignee else None,
        created_by=creator.id,
    )
    db.add(issue)
    await _record_change(
        db,
        issue_id=issue.id,
        field_name="status",
        old_value=None,
        new_value=ISSUE_STATUS_OPEN,
        changed_by=creator.id,
        reason="created",
        changed_at=issue.updated_at,
    )
    await db.commit()
    await db.refresh(issue)
    return issue


async def list_issues(
    db: AsyncSession,
    *,
    status: str | None = None,
    aspect: str | None = None,
    assignee: str | None = None,
    dataset_version: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Issue], int]:
    stmt = select(Issue)
    count_stmt = select(func.count()).select_from(Issue)
    if status:
        stmt = stmt.where(Issue.status == status)
        count_stmt = count_stmt.where(Issue.status == status)
    if aspect:
        stmt = stmt.where(Issue.aspect == aspect)
        count_stmt = count_stmt.where(Issue.aspect == aspect)
    if assignee:
        stmt = stmt.where(Issue.assignee == assignee)
        count_stmt = count_stmt.where(Issue.assignee == assignee)
    if dataset_version:
        stmt = stmt.where(Issue.dataset_version == dataset_version)
        count_stmt = count_stmt.where(Issue.dataset_version == dataset_version)
    total = (await db.execute(count_stmt)).scalar_one()
    result = await db.execute(
        stmt.order_by(Issue.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), int(total)


async def get_issue(db: AsyncSession, issue_id: str) -> Issue | None:
    return await db.get(Issue, issue_id)


async def get_issue_history(
    db: AsyncSession, issue_id: str
) -> list[IssueHistory]:
    result = await db.execute(
        select(IssueHistory)
        .where(IssueHistory.issue_id == issue_id)
        .order_by(IssueHistory.changed_at.asc())
    )
    return list(result.scalars().all())


async def _record_change(
    db: AsyncSession,
    *,
    issue_id: str,
    field_name: str,
    old_value: str | None,
    new_value: str | None,
    changed_by: str,
    reason: str | None,
    changed_at: datetime | None = None,
) -> None:
    if old_value == new_value:
        return
    db.add(
        IssueHistory(
            id=str(uuid4()),
            issue_id=issue_id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            changed_by=changed_by,
            changed_at=changed_at or datetime.now(UTC),
            reason=reason,
        )
    )


async def transition_issue(
    db: AsyncSession, issue: Issue, *, req, operator: User
) -> Issue:
    """推进问题卡状态机。"""
    target = req.status
    if target == issue.status:
        raise ValueError(f"状态已是 {target}")
    allowed = ISSUE_TRANSITIONS.get(issue.status, set())
    if target not in allowed:
        raise ValueError(
            f"不允许从 {issue.status} 流转到 {target}"
        )

    now = datetime.now(UTC)
    reason = f"transition:{issue.status}->{target}"

    # 依据目标状态的必填校验
    if target == ISSUE_STATUS_IN_PROGRESS and issue.status == ISSUE_STATUS_OPEN:
        if not (req.resolution_note or "").strip():
            raise ValueError("进入处置必须先填写处置说明 resolution_note")
        if req.resolution_note != issue.resolution_note:
            await _record_change(
                db, issue_id=issue.id, field_name="resolution_note",
                old_value=issue.resolution_note, new_value=req.resolution_note,
                changed_by=operator.id, reason=reason, changed_at=now,
            )
            issue.resolution_note = req.resolution_note
    if target == ISSUE_STATUS_CLOSED:
        if issue.status != ISSUE_STATUS_PENDING_VALIDATION:
            raise ValueError("关闭前必须先进入 pending_validation")
        if not (req.validation_note or "").strip():
            raise ValueError("关闭必须填写验证结论 validation_note")
        if req.validation_note != issue.validation_note:
            await _record_change(
                db, issue_id=issue.id, field_name="validation_note",
                old_value=issue.validation_note, new_value=req.validation_note,
                changed_by=operator.id, reason=reason, changed_at=now,
            )
            issue.validation_note = req.validation_note
        issue.closed_at = now

    # 记录状态变更
    await _record_change(
        db, issue_id=issue.id, field_name="status",
        old_value=issue.status, new_value=target,
        changed_by=operator.id, reason=reason, changed_at=now,
    )

    issue.status = target
    issue.updated_at = now
    await db.commit()
    await db.refresh(issue)
    return issue


# ---------- 效果回测 ----------


async def retrospect_issue(
    db: AsyncSession, issue: Issue
) -> dict:
    """关闭后回测：对比创建前后该属性差评率。

    - pre_rate：issue 所属数据集在创建时间之前的差评率。
    - post_rate：最新数据集在创建时间之后的差评率。
    - change = post_rate - pre_rate；improved = post_rate < pre_rate。
    """
    if issue.status != ISSUE_STATUS_CLOSED:
        raise ValueError("仅已关闭的问题卡可进行效果回测")

    pre_rate = await _aspect_negative_rate(
        db,
        dataset_version=issue.dataset_version,
        aspect=issue.aspect,
        end_date=issue.created_at or datetime.now(UTC),
    )
    latest = await get_latest_dataset(db)
    post_dataset = latest.dataset_version if latest else issue.dataset_version
    post_rate = await _aspect_negative_rate(
        db,
        dataset_version=post_dataset,
        aspect=issue.aspect,
        start_date=issue.created_at or datetime.now(UTC),
    )
    change = round(post_rate - pre_rate, 4)
    return {
        "issue_id": issue.id,
        "dataset_version": issue.dataset_version,
        "aspect": issue.aspect,
        "pre_rate": pre_rate,
        "post_rate": post_rate,
        "change": change,
        "improved": post_rate < pre_rate,
    }
