"""人工审核工作流 API 路由（M5）。

端点：
  GET  /api/v1/review-tasks                      审核任务列表（按状态/采样组筛选）
  GET  /api/v1/review-tasks/next                 下一条待审核（连续审核）
  GET  /api/v1/review-tasks/summary              审核进度统计
  POST /api/v1/review-tasks/generate             从预测结果生成审核任务（analyst+）
  GET  /api/v1/review-tasks/{id}                 任务详情（含原始评论引用）
  PATCH  /api/v1/review-tasks/{id}               提交审核结果（operator+）
  POST  /api/v1/review-tasks/{id}/second-review  二次复核（analyst+）

注意：静态路径（next/summary/generate）须声明在 {id} 参数路由之前。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_db
from app.models.user import User
from app.schemas.review_task import (
    GenerateTasksRequest,
    GenerateTasksResponse,
    ReviewTaskListItem,
    ReviewTaskListResponse,
    ReviewTaskOut,
    SecondReviewRequest,
    SubmitReviewRequest,
    SummaryResponse,
)
from app.services import review_task_service

router = APIRouter(prefix="/api/v1/review-tasks", tags=["review-tasks"])

OpsUser = Annotated[User, Depends(require_role("operator", "analyst", "admin"))]
AnalystUser = Annotated[User, Depends(require_role("analyst", "admin"))]
AnyUser = Annotated[User, Depends(get_current_user)]


def _to_out(task, review) -> ReviewTaskOut:
    out = ReviewTaskOut.model_validate(task)
    if review is not None:
        out.review_title = review.review_title
        out.review_text = review.review_text
        out.rating = review.rating
    return out


@router.post("/generate", status_code=201)
async def generate_tasks(
    req: GenerateTasksRequest,
    _: AnalystUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """从预测结果生成审核任务。"""
    try:
        result = await review_task_service.generate_tasks(
            db,
            dataset_version=req.dataset_version,
            model_version=req.model_version,
            count=req.count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {
        "code": 0,
        "data": GenerateTasksResponse(
            created=result["created"],
            dataset_version=req.dataset_version,
            skipped=result["skipped"],
        ),
    }


@router.get("")
async def list_review_tasks(
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = None,
    sampling_group: str | None = None,
    dataset_version: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    items, total = await review_task_service.list_tasks(
        db,
        status=status,
        sampling_group=sampling_group,
        dataset_version=dataset_version,
        page=page,
        page_size=page_size,
    )
    return {
        "code": 0,
        "data": ReviewTaskListResponse(
            items=[ReviewTaskListItem.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        ),
    }


@router.get("/next")
async def get_next_task(
    _: OpsUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    dataset_version: str | None = None,
) -> dict:
    task = await review_task_service.get_next_task(db, dataset_version=dataset_version)
    if task is None:
        return {"code": 0, "data": None}
    review = await review_task_service.get_review_quote(db, task)
    return {"code": 0, "data": _to_out(task, review)}


@router.get("/summary")
async def get_summary(
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    dataset_version: str | None = None,
) -> dict:
    data = await review_task_service.summary(db, dataset_version=dataset_version)
    return {"code": 0, "data": SummaryResponse.model_validate(data)}


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    task = await review_task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="审核任务不存在")
    review = await review_task_service.get_review_quote(db, task)
    return {"code": 0, "data": _to_out(task, review)}


@router.patch("/{task_id}")
async def submit_review(
    task_id: str,
    req: SubmitReviewRequest,
    user: OpsUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    task = await review_task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="审核任务不存在")
    try:
        updated = await review_task_service.submit_review(
            db,
            task,
            user,
            status=req.status,
            reviewer_sentiment=req.reviewer_sentiment,
            reviewer_aspects=req.reviewer_aspects,
            review_reason=req.review_reason,
            review_note=req.review_note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    review = await review_task_service.get_review_quote(db, updated)
    return {"code": 0, "data": _to_out(updated, review)}


@router.post("/{task_id}/second-review")
async def second_review(
    task_id: str,
    req: SecondReviewRequest,
    user: AnalystUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    task = await review_task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="审核任务不存在")
    try:
        updated = await review_task_service.second_review(
            db, task, user, status=req.status, review_note=req.review_note
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"code": 0, "data": ReviewTaskOut.model_validate(updated)}
