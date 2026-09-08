"""评论搜索/聚合 API 路由（M3 评论搜索引擎）。

端点：
  POST /api/v1/reviews/search     全文搜索（IK 分词 + 高亮）
  POST /api/v1/reviews/aggregate  分面聚合（属性/评分/时间/情感）

响应约定与 M1/M2 一致：{"code": 0, "data": ...}，登录即可访问。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.search import AggregateRequest, SearchRequest
from app.services import search_service

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])

AnyUser = Annotated[User, Depends(get_current_user)]


@router.post("/search")
async def search_reviews(req: SearchRequest, _: AnyUser) -> dict:
    """全文搜索评论，返回带关键词高亮的分页结果。"""
    try:
        result = await search_service.search_reviews(req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except search_service.SearchUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return {"code": 0, "data": result}


@router.post("/aggregate")
async def aggregate_reviews(req: AggregateRequest, _: AnyUser) -> dict:
    """分面聚合：属性差评率、评分分布、时间趋势、情感分布。"""
    try:
        result = await search_service.aggregate_reviews(req)
    except search_service.SearchUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return {"code": 0, "data": result}
