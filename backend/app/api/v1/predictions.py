"""预测 API 路由（M4 NLP 分析管线）。

端点：
  POST /api/v1/predictions/batch            触发批量推理（analyst+）
  GET  /api/v1/predictions                  查询预测结果（分页）
  GET  /api/v1/predictions/low-confidence   置信度过低列表（供 M5 审核）

响应约定与 M1 一致：{"code": 0, "data": ...}。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_db
from app.models.user import User
from app.schemas.prediction import (
    BatchInferenceRequest,
    BatchInferenceResponse,
    LowConfidenceOut,
    PredictionListResponse,
    PredictionOut,
)
from app.services import prediction_service

router = APIRouter(prefix="/api/v1/predictions", tags=["predictions"])

PublicationUser = Annotated[User, Depends(require_role("operator", "analyst", "admin"))]
AnyUser = Annotated[User, Depends(get_current_user)]


@router.post("/batch", status_code=202)
async def trigger_batch_inference(
    req: BatchInferenceRequest,
    _: PublicationUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """触发指定数据集的批量推理。"""
    try:
        result = await prediction_service.submit_batch_inference(
            db, req.dataset_version, req.model_version
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {
        "code": 0,
        "data": BatchInferenceResponse(
            status="queued",
            message="推理任务已提交",
            dataset_version=req.dataset_version,
            model_version=req.model_version,
            job_id=result["job_id"],
        ),
    }


@router.get("")
async def list_predictions(
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    dataset_version: str | None = None,
    model_version: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    items, total = await prediction_service.list_predictions(
        db,
        dataset_version=dataset_version,
        model_version=model_version,
        page=page,
        page_size=page_size,
    )
    return {
        "code": 0,
        "data": PredictionListResponse(
            items=[PredictionOut.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        ),
    }


@router.get("/low-confidence")
async def list_low_confidence(
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    dataset_version: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    items, total = await prediction_service.list_low_confidence(
        db, dataset_version=dataset_version, page=page, page_size=page_size
    )
    return {
        "code": 0,
        "data": {
            "items": [LowConfidenceOut.model_validate(i) for i in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }
