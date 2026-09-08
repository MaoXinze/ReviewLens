"""训练运行 API 路由（M4 训练编排 + M6 模型管理）。

M4 端点：
  POST /api/v1/analysis-runs                创建训练运行（弱标签，analyst+）
  GET  /api/v1/analysis-runs                训练运行列表（分页）
  GET  /api/v1/analysis-runs/{id}           训练运行详情
  POST /api/v1/analysis-runs/{id}/publish   发布模型（analyst+）

M6 端点：
  POST /api/v1/analysis-runs/reviewed       用 approved/verified 审核样本训练
  POST /api/v1/analysis-runs/{id}/rollback  回滚到上一发布版本（analyst+）
  GET  /api/v1/models/current               当前生产模型
  GET  /api/v1/models/history               模型版本历史
  GET  /api/v1/models/{id}/criteria         发布门槛检查

响应约定与 M1 一致：{"code": 0, "data": ...}。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_db
from app.models.user import User
from app.schemas.model import (
    CurrentModelResponse,
    ModelHistoryResponse,
    ModelOut,
    PublishCriteriaResponse,
    PublishModelResponse,
    ReviewedTrainingRequest,
    RollbackModelResponse,
)
from app.schemas.prediction import (
    AnalysisRunListResponse,
    AnalysisRunOut,
    CreateAnalysisRunRequest,
)
from app.services import analysis_service, model_service, nlp_client

router = APIRouter(prefix="/api/v1", tags=["analysis-runs"])

AnalystUser = Annotated[User, Depends(require_role("analyst", "operator", "admin"))]
AnyUser = Annotated[User, Depends(get_current_user)]


def _run_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="训练运行不存在")


@router.post("/analysis-runs")
async def create_analysis_run(
    req: CreateAnalysisRunRequest,
    user: AnalystUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """触发一次训练运行（采样弱标签 → NLP 训练 → 记录指标）。"""
    try:
        run = await analysis_service.create_run(
            db,
            dataset_version=req.dataset_version,
            created_by=user.id,
            algorithm=req.algorithm,
            min_samples=req.min_samples,
        )
    except (ValueError, nlp_client.NLPUnavailable, nlp_client.NLPRemoteError) as exc:
        is_remote = isinstance(
            exc, (nlp_client.NLPUnavailable, nlp_client.NLPRemoteError)
        )
        status = 502 if is_remote else 400
        raise HTTPException(status_code=status, detail=str(exc)) from None
    return {"code": 0, "data": AnalysisRunOut.model_validate(run)}


@router.post("/analysis-runs/reviewed")
async def create_reviewed_analysis_run(
    req: ReviewedTrainingRequest,
    user: AnalystUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """用 approved/verified 人工审核样本触发训练（M6 验收标准 1）。"""
    try:
        run = await model_service.create_reviewed_run(
            db,
            dataset_version=req.dataset_version,
            created_by=user.id,
            algorithm=req.algorithm,
            min_samples=req.min_samples,
        )
    except (ValueError, nlp_client.NLPUnavailable, nlp_client.NLPRemoteError) as exc:
        is_remote = isinstance(
            exc, (nlp_client.NLPUnavailable, nlp_client.NLPRemoteError)
        )
        status = 502 if is_remote else 400
        raise HTTPException(status_code=status, detail=str(exc)) from None
    return {"code": 0, "data": AnalysisRunOut.model_validate(run)}


@router.get("/analysis-runs")
async def list_analysis_runs(
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    dataset_version: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    items, total = await analysis_service.list_runs(
        db, dataset_version=dataset_version, page=page, page_size=page_size
    )
    return {
        "code": 0,
        "data": AnalysisRunListResponse(
            items=[AnalysisRunOut.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        ),
    }


@router.get("/analysis-runs/{run_id}")
async def get_analysis_run(
    run_id: str,
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    run = await analysis_service.get_run(db, run_id)
    if run is None:
        raise _run_not_found()
    return {"code": 0, "data": AnalysisRunOut.model_validate(run)}


@router.post("/analysis-runs/{run_id}/publish")
async def publish_analysis_run(
    run_id: str,
    _: AnalystUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """发布模型：校验全部门槛并下线旧生产模型。"""
    run = await analysis_service.get_run(db, run_id)
    if run is None:
        raise _run_not_found()
    try:
        message = await model_service.publish_model(db, run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {
        "code": 0,
        "data": PublishModelResponse(
            status="published" if run.publish_status == "published" else "unchanged",
            message=message,
            model_version=run.model_version,
        ),
    }


@router.post("/analysis-runs/{run_id}/rollback")
async def rollback_analysis_run(
    run_id: str,
    _: AnalystUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """回滚到上一发布版本。"""
    run = await analysis_service.get_run(db, run_id)
    if run is None:
        raise _run_not_found()
    try:
        prev = await model_service.rollback_model(db, run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {
        "code": 0,
        "data": RollbackModelResponse(
            message=(
                "已回滚到上一发布版本"
                if prev
                else "已下线当前模型，无上一发布版本"
            ),
            previous_model_version=prev.model_version if prev else None,
            has_previous=prev is not None,
        ),
    }


@router.get("/models/current")
async def get_current_model(
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """当前生产模型（DB 驱动，取代只读 NLP 服务）。"""
    model = await model_service.get_current_model(db)
    if model is None:
        return {"code": 0, "data": CurrentModelResponse(publish_status="no_model")}
    return {
        "code": 0,
        "data": CurrentModelResponse(
            model_version=model.model_version,
            algorithm=model.algorithm,
            macro_f1=model.macro_f1,
            publish_status=model.publish_status,
        ),
    }


@router.get("/models/history")
async def list_model_history(
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """模型版本历史。"""
    items = await model_service.list_model_history(db)
    return {
        "code": 0,
        "data": ModelHistoryResponse(
            items=[ModelOut.model_validate(i) for i in items], total=len(items)
        ),
    }


@router.get("/models/{run_id}/criteria")
async def get_publish_criteria(
    run_id: str,
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """发布会话门槛检查（返回各门槛是否满足及原因，供前端预判）。"""
    run = await analysis_service.get_run(db, run_id)
    if run is None:
        raise _run_not_found()

    ok, reason = await model_service.check_publish_criteria(db, run)
    coverage = await model_service.calculate_review_coverage(db, run.dataset_version)
    reasons: list[str] = [reason] if not ok else ["全部门槛满足，可发布"]

    return {
        "code": 0,
        "data": PublishCriteriaResponse(
            macro_f1=run.macro_f1,
            macro_f1_ok=(run.macro_f1 or 0) >= model_service.PUBLISH_MACRO_F1,
            test_samples=run.test_samples or 0,
            test_samples_ok=(run.test_samples or 0)
            >= model_service.PUBLISH_MIN_TEST_SAMPLES,
            coverage=round(coverage, 4),
            coverage_ok=coverage >= model_service.PUBLISH_MIN_COVERAGE,
            can_publish=ok,
            reasons=reasons,
            metrics={
                "classification_report": run.classification_report,
                "confusion_matrix": run.confusion_matrix,
                "macro_f1": run.macro_f1,
                "accuracy": run.accuracy,
            },
        ),
    }
