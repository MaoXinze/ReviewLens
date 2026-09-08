"""M7 体验洞察看板 API 路由。

端点：
  GET /api/v1/insights/overview        总览（评论量/情感分布/差评属性/审核进度）
  GET /api/v1/insights/aspect-ranking  属性差评率排行 + 环比
  GET /api/v1/insights/trends          属性差评率趋势（周/月）
  GET /api/v1/insights/sku-comparison  多 SKU 属性对比
  GET /api/v1/insights/evidence        聚合数字 → 证据评论下钻

响应约定与 M1-M6 一致：{"code": 0, "data": ...}，登录即可访问。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.user import User
from app.schemas.insight import Granularity
from app.services import insight_service

router = APIRouter(prefix="/api/v1/insights", tags=["insights"])

AnyUser = Annotated[User, Depends(get_current_user)]


@router.get("/overview")
async def overview(
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    dataset_version: str = Query(...),
    product_id: str | None = None,
) -> dict:
    """总览看板（评论量/情感分布/差评属性 top/审核进度）。"""
    try:
        result = await insight_service.get_overview(
            db, dataset_version, product_id=product_id
        )
    except insight_service.InsightUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return {"code": 0, "data": result}


@router.get("/aspect-ranking")
async def aspect_ranking(
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    dataset_version: str = Query(...),
    product_id: str | None = None,
    period: str | None = None,
) -> dict:
    """属性差评率排行 + 上一同等月窗口环比。"""
    try:
        result = await insight_service.get_aspect_ranking(
            db, dataset_version, product_id=product_id, period=period
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except insight_service.InsightUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return {"code": 0, "data": result}


@router.get("/trends")
async def trends(
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    dataset_version: str = Query(...),
    granularity: Granularity = Query("month"),
    product_id: str | None = None,
    aspect: str | None = None,
    period: str | None = None,
) -> dict:
    """属性差评率趋势时间序列（分层下钻：年→月→周→日）。

    granularity 决定聚合与窗口：
      - month + period='2025'        → 该年 12 个月
      - week  + period='2025-08'     → 该月内周
      - day   + period='2025-08-11'  → 该日期所在周 7 天
    """
    try:
        result = await insight_service.get_trends(
            db,
            dataset_version,
            product_id=product_id,
            aspect=aspect,
            granularity=granularity,
            period=period,
        )
    except insight_service.InsightUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return {"code": 0, "data": result}


@router.get("/sku-comparison")
async def sku_comparison(
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    dataset_version: str = Query(...),
    skus: str = Query(..., min_length=1),
    aspect: str | None = None,
) -> dict:
    """多 SKU 属性对比。skus 逗号分隔。"""
    sku_list = [sku.strip() for sku in skus.split(",") if sku.strip()]
    try:
        result = await insight_service.get_sku_comparison(
            db, dataset_version, sku_list, aspect=aspect
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except insight_service.InsightUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return {"code": 0, "data": result}


@router.get("/evidence")
async def evidence(
    _: AnyUser,
    dataset_version: str = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    product_id: str | None = None,
    aspect: str | None = None,
    sentiment: str | None = None,
    period: str | None = None,
) -> dict:
    """聚合数字 → 证据评论列表（与聚合同过滤条件）。"""
    try:
        result = await insight_service.get_evidence(
            dataset_version,
            page=page,
            page_size=page_size,
            product_id=product_id,
            aspect=aspect,
            sentiment=sentiment,
            period=period,
        )
    except insight_service.InsightUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return {"code": 0, "data": result}
