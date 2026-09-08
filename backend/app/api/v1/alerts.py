"""M9 告警 API 路由。

端点：
  POST  /api/v1/alert-rules            创建告警规则（analyst+）
  GET   /api/v1/alert-rules            规则列表（登录）
  PATCH /api/v1/alert-rules/{id}       更新规则：暂停/恢复 active↔paused（analyst+）
  GET   /api/v1/alerts                 告警列表（登录，可按状态筛选）
  PATCH /api/v1/alerts/{id}            确认/解决告警
                                        active→acknowledged→resolved（operator+）

响应约定：{"code": 0, "data": ...}。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_db
from app.models.alert import Alert, AlertRule
from app.models.user import User
from app.schemas.alert import (
    AlertListResponse,
    AlertOut,
    AlertRuleCreateRequest,
    AlertRuleListResponse,
    AlertRuleOut,
    AlertRuleUpdateRequest,
    AlertUpdateRequest,
)
from app.services import alert_service

router = APIRouter(prefix="/api/v1/alert-rules", tags=["alerts"])
alerts_router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

AnalystUser = Annotated[
    User, Depends(require_role("analyst", "admin"))
]
OpsUser = Annotated[
    User, Depends(require_role("operator", "analyst", "admin"))
]
AnyUser = Annotated[User, Depends(get_current_user)]


# ---------- 告警规则 ----------


@router.post("", status_code=201)
async def create_rule(
    req: AlertRuleCreateRequest,
    user: AnalystUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    try:
        rule = await alert_service.create_rule(db, req=req, creator=user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"code": 0, "data": AlertRuleOut.model_validate(rule)}


@router.get("")
async def list_rules(
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    items, total = await alert_service.list_rules(
        db, status=status, page=page, page_size=page_size
    )
    return {
        "code": 0,
        "data": AlertRuleListResponse(
            items=[AlertRuleOut.model_validate(r) for r in items],
            total=total,
            page=page,
            page_size=page_size,
        ),
    }


@router.patch("/{rule_id}")
async def update_rule(
    rule_id: str,
    req: AlertRuleUpdateRequest,
    _: AnalystUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    rule = await alert_service.get_rule(db, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="告警规则不存在")
    try:
        updated = await alert_service.update_rule_status(
            db, rule, status=req.status
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"code": 0, "data": AlertRuleOut.model_validate(updated)}


# ---------- 告警 ----------


async def _attach_rules(db: AsyncSession, alerts: list) -> dict[str, AlertRule]:
    """批量查询规则并挂载 name/type 到告警对象。"""
    rule_ids = {a.rule_id for a in alerts} if alerts else set()
    if not rule_ids:
        return {}
    result = await db.execute(
        select(AlertRule).where(AlertRule.id.in_(rule_ids))
    )
    return {r.id: r for r in result.scalars().all()}


@alerts_router.get("")
async def list_alerts(
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    try:
        items, total = await alert_service.list_alerts(
            db, status=status, page=page, page_size=page_size
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    rules_by_id = await _attach_rules(db, items)
    out = []
    for a in items:
        rule = rules_by_id.get(a.rule_id)
        payload = AlertOut.model_validate(a)
        if rule is not None:
            payload.rule_name = rule.name
            payload.rule_type = rule.rule_type
        out.append(payload)
    return {
        "code": 0,
        "data": AlertListResponse(
            items=out, total=total, page=page, page_size=page_size
        ),
    }


@alerts_router.patch("/{alert_id}")
async def update_alert(
    alert_id: str,
    req: AlertUpdateRequest,
    user: OpsUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="告警不存在")
    try:
        updated = await alert_service.update_alert_status(
            db, alert, status=req.status, operator=user
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"code": 0, "data": AlertOut.model_validate(updated)}
