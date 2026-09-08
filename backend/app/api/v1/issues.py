"""问题卡管理 API 路由（M8）。

端点：
  POST  /api/v1/issues                  创建问题卡（operator+）
  GET   /api/v1/issues                  问题卡列表（按状态/属性/负责人筛选）
  GET   /api/v1/issues/{id}             问题卡详情（含审计轨迹）
  PATCH /api/v1/issues/{id}             推进问题卡状态（operator+）
  POST  /api/v1/issues/{id}/retrospect  效果回测（operator+）

鉴权：创建/推进/回测为 operator+，查询登录即可。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_db
from app.models.user import User
from app.schemas.issue import (
    IssueCreateRequest,
    IssueListItem,
    IssueListResponse,
    IssueOut,
    IssueUpdateRequest,
    RetrospectResponse,
)
from app.services import issue_service

router = APIRouter(prefix="/api/v1/issues", tags=["issues"])

OpsUser = Annotated[User, Depends(require_role("operator", "analyst", "admin"))]
AnyUser = Annotated[User, Depends(get_current_user)]


@router.post("", status_code=201)
async def create_issue(
    req: IssueCreateRequest,
    user: OpsUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    creator = user
    assignee = None
    if req.assignee:
        assignee = await db.get(User, req.assignee)
        if assignee is None or not assignee.is_active:
            raise HTTPException(status_code=400, detail="负责人不存在或已禁用")
    try:
        issue = await issue_service.create_issue(
            db, req=req, creator=creator, assignee=assignee
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"code": 0, "data": IssueOut.model_validate(issue)}


@router.get("")
async def list_issues(
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = None,
    aspect: str | None = None,
    assignee: str | None = None,
    dataset_version: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    items, total = await issue_service.list_issues(
        db,
        status=status,
        aspect=aspect,
        assignee=assignee,
        dataset_version=dataset_version,
        page=page,
        page_size=page_size,
    )
    return {
        "code": 0,
        "data": IssueListResponse(
            items=[IssueListItem.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        ),
    }


@router.get("/{issue_id}")
async def get_issue(
    issue_id: str,
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    issue = await issue_service.get_issue(db, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="问题卡不存在")
    history = await issue_service.get_issue_history(db, issue_id)
    return {
        "code": 0,
        "data": {
            "issue": IssueOut.model_validate(issue),
            "history": [
                {
                    "field_name": h.field_name,
                    "old_value": h.old_value,
                    "new_value": h.new_value,
                    "changed_by": h.changed_by,
                    "changed_at": h.changed_at,
                    "reason": h.reason,
                }
                for h in history
            ],
        },
    }


@router.patch("/{issue_id}")
async def update_issue(
    issue_id: str,
    req: IssueUpdateRequest,
    user: OpsUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    issue = await issue_service.get_issue(db, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="问题卡不存在")
    try:
        updated = await issue_service.transition_issue(
            db, issue, req=req, operator=user
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"code": 0, "data": IssueOut.model_validate(updated)}


@router.post("/{issue_id}/retrospect")
async def retrospect_issue(
    issue_id: str,
    _: OpsUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    issue = await issue_service.get_issue(db, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="问题卡不存在")
    try:
        result = await issue_service.retrospect_issue(db, issue)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"code": 0, "data": RetrospectResponse.model_validate(result)}
