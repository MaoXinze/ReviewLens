"""M9 导出 API 路由。

端点：
  POST /api/v1/exports              导出 CSV（analyst+）
  GET  /api/v1/exports              导出记录列表（登录）
  GET  /api/v1/exports/{id}/download  下载导出文件（analyst+）

下载返回 text/csv 流式文件；文件名沿用 MinIO 存储名（basename）。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_db
from app.models.user import User
from app.schemas.alert import (
    ExportCreateRequest,
    ExportListResponse,
    ExportRecordOut,
)
from app.services import export_service

router = APIRouter(prefix="/api/v1/exports", tags=["exports"])

AnalystUser = Annotated[
    User, Depends(require_role("analyst", "admin"))
]
AnyUser = Annotated[User, Depends(get_current_user)]


@router.post("", status_code=201)
async def create_export(
    req: ExportCreateRequest,
    user: AnalystUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    try:
        record = await export_service.export_reviews(db, req=req, user_id=user.id)
    except Exception as exc:  # MinIO 不可用 / 存储失败
        raise HTTPException(status_code=503, detail=f"导出失败: {exc}") from None
    return {"code": 0, "data": ExportRecordOut.model_validate(record)}


@router.get("")
async def list_exports(
    _: AnyUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    items, total = await export_service.list_exports(
        db, page=page, page_size=page_size
    )
    return {
        "code": 0,
        "data": ExportListResponse(
            items=[ExportRecordOut.model_validate(r) for r in items],
            total=total,
            page=page,
            page_size=page_size,
        ),
    }


@router.get("/{export_id}/download")
async def download_export(
    export_id: str,
    _: AnalystUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    record = await export_service.get_export_record(db, export_id)
    if record is None:
        raise HTTPException(status_code=404, detail="导出记录不存在")
    try:
        data = await export_service.download_bytes(record)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"文件读取失败: {exc}") from None
    filename = record.file_path.rsplit("/", 1)[-1] or "export.csv"
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
