"""数据集 API 路由（M2 数据导入引擎）。

端点：
  POST /api/v1/datasets/imports     上传 CSV/JSONL，触发异步导入(operator+)
  GET  /api/v1/datasets                             数据集列表（分页）
  GET  /api/v1/datasets/{version}                   数据集详情 + 质量报告
  GET  /api/v1/datasets/{version}/reviews           数据集内评论列表
  GET  /api/v1/datasets/{version}/quality-report    质量报告详情

响应约定与 M1 一致：{"code": 0, "data": ...}。
"""
import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_db
from app.models.user import User
from app.schemas.dataset import DatasetOut, ReviewOut
from app.services import dataset_service, review_service

router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])

PublicationUser = Annotated[
    User, Depends(require_role("operator", "analyst", "admin"))
]
AnyUser = Annotated[User, Depends(get_current_user)]


@router.post("/imports", status_code=202)
async def import_dataset(
    user: PublicationUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
    field_mapping: Annotated[str | None, Form()] = None,
) -> dict:
    """上传评论文件并触发异步导入。"""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")

    mapping: dict | None = None
    if field_mapping:
        try:
            mapping = json.loads(field_mapping)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=422, detail="field_mapping 不是合法 JSON"
            ) from None
        if not isinstance(mapping, dict):
            raise HTTPException(
                status_code=422, detail="field_mapping 必须是 JSON 对象"
            )

    result = await dataset_service.submit_import(
        db,
        content=content,
        filename=file.filename or "upload",
        field_mapping=mapping,
        created_by=user.id,
    )
    return {"code": 0, "data": result}


@router.get("")
async def list_datasets(
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    items, total = await review_service.list_datasets(
        db, page=page, page_size=page_size
    )
    return {
        "code": 0,
        "data": {
            "items": [DatasetOut.model_validate(i) for i in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.get("/{version}")
async def get_dataset(
    version: str,
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    dataset = await review_service.get_dataset(db, version)
    if dataset is None:
        raise HTTPException(status_code=404, detail="数据集不存在")
    return {"code": 0, "data": DatasetOut.model_validate(dataset)}


@router.get("/{version}/quality-report")
async def get_quality_report(
    version: str,
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    dataset = await review_service.get_dataset(db, version)
    if dataset is None:
        raise HTTPException(status_code=404, detail="数据集不存在")
    report = dataset.quality_report or {"rejection_reasons": {}, "reasons_detail": {}}
    return {"code": 0, "data": report}


@router.get("/{version}/products")
async def list_dataset_products(
    version: str,
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    """数据集内评论量最高的商品（SKU）列表（供 SKU 对比选择）。"""
    if await review_service.get_dataset(db, version) is None:
        raise HTTPException(status_code=404, detail="数据集不存在")
    items = await review_service.list_products(db, version=version, limit=limit)
    return {"code": 0, "data": {"items": items}}


@router.get("/{version}/reviews")
async def list_dataset_reviews(
    version: str,
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    items, total = await review_service.list_reviews(
        db, version=version, page=page, page_size=page_size
    )
    return {
        "code": 0,
        "data": {
            "items": [ReviewOut.model_validate(i) for i in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }
