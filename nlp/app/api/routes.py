"""NLP 服务 API 路由（内部服务，仅 backend 调用，不对前端开放）。

端点：
  POST /api/v1/inference/batch      批量推理（评论文本 → 整体情感 + 属性级情感）
  POST /api/v1/training-runs       训练新模型（接收标注样本，返回指标）
  GET  /api/v1/training-runs/{id}  查询训练运行
  GET  /api/v1/models/{version}    模型信息（含指标）
  GET  /api/v1/models/current      当前生产模型

推理采用分层策略（P7.4/M11）：基线 TF-IDF+LR 常驻处理高置信样本，
仅当基线置信度低于 cascade_theta_high 时，才送 DistilBERT 深度模型复核，
在精度与成本/时延间取平衡。深度模型惰性加载，未命中时不常驻内存。
"""

import asyncio
import glob
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services import training
from app.services.aspect_extractor import RuleBasedAspectExtractor
from app.services.cascade import CascadeInference
from app.services.distilbert_trainer import DistilBertSentimentClassifier
from app.services.sentiment_classifier import TfidfLrSentimentClassifier

router = APIRouter(prefix="/api/v1", tags=["nlp"])

_extractor: RuleBasedAspectExtractor | None = None
# 分层推理器（惰性初始化，缓存复用）
_cascade: CascadeInference | None = None
_cascade_version: str | None = None


def _get_extractor() -> RuleBasedAspectExtractor:
    global _extractor
    if _extractor is None:
        _extractor = RuleBasedAspectExtractor(settings.taxonomy_file)
    return _extractor


def _latest_baseline_path() -> Path | None:
    """取 model_dir 中最新的 TF-IDF 基线 .joblib（P6 训练产物）。"""
    candidates = glob.glob(str(Path(settings.model_dir) / "tfidf_lr_*.joblib"))
    if not candidates:
        return None
    return max((Path(p) for p in candidates), key=lambda p: p.stat().st_mtime)


def _get_cascade() -> CascadeInference | None:
    """惰性构建分层推理器；任一依赖缺失时返回 None 回退原逻辑。

    深度模型仅在首次真正需要时加载（transformers 惰性导入 + 读盘），
    高置信流量全程不触达深度模型，避免其常驻内存。
    """
    global _cascade, _cascade_version
    if _cascade is not None:
        return _cascade
    if not settings.cascade_enabled:
        return None

    base_path = _latest_baseline_path()
    if base_path is None:
        return None
    deep_path = Path(settings.cascade_deep_model)
    if not (deep_path / "model.safetensors").exists():
        return None

    try:
        baseline = TfidfLrSentimentClassifier()
        baseline.load(str(base_path))
        deep = DistilBertSentimentClassifier()
        deep.load(str(deep_path))
        _cascade = CascadeInference(
            baseline, deep, theta_high=settings.cascade_theta_high
        )
        _cascade_version = deep_path.name
    except RuntimeError:
        _cascade = None
        _cascade_version = "baseline"
    return _cascade


# ---------- Schemas ----------


class ReviewInput(BaseModel):
    review_id: str
    text: str = Field(default="", max_length=5000)


class InferenceRequest(BaseModel):
    reviews: list[ReviewInput] = Field(min_length=1, max_length=1000)


class InferenceResult(BaseModel):
    review_id: str
    overall_sentiment: str
    confidence: float
    aspects: list[dict]
    model_version: str | None = None


class InferenceResponse(BaseModel):
    predictions: list[InferenceResult]


class TrainingSample(BaseModel):
    text: str = Field(max_length=5000)
    label: str  # positive/neutral/negative


class TrainingRequest(BaseModel):
    samples: list[TrainingSample] = Field(min_length=1)
    test_size: float | None = Field(default=None, gt=0, lt=1)
    random_seed: int | None = None


# ---------- Product 逻辑 ----------


def _predict_one(review_id: str, text: str) -> InferenceResult:
    extractor = _get_extractor()
    aspects = extractor.extract(text)

    model, version = training.get_current()
    if model is not None:
        try:
            overall = model.predict([text])[0]
        except RuntimeError:
            overall = extractor.infer_overall(text)
    else:
        overall = extractor.infer_overall(text)
    return InferenceResult(
        review_id=review_id,
        overall_sentiment=overall["sentiment"],
        confidence=round(overall["confidence"], 6),
        aspects=aspects,
        model_version=version,
    )


# ---------- Routes ----------


def _predict_batch_sync(req: InferenceRequest) -> InferenceResponse:
    """批量推理主体（CPU 密集同步代码），由路由经 asyncio.to_thread 调用。

    分层策略：基线置信 ≥ θ 直接采用；低置信样本送深度模型复核。
    深度模型不可用时无缝回退为纯基线/规则路径，接口契约不变。
    """
    cascade = _get_cascade()
    if cascade is not None:
        texts = [r.text for r in req.reviews]
        out = cascade.predict(texts)
        by_index = {res["index"]: res for res in out["results"]}
        extractor = _get_extractor()
        predictions = []
        for i, rev in enumerate(req.reviews):
            res = by_index[i]
            predictions.append(
                InferenceResult(
                    review_id=rev.review_id,
                    overall_sentiment=res["sentiment"],
                    confidence=res["confidence"],
                    aspects=extractor.extract(rev.text),
                    model_version=_cascade_version,
                )
            )
        return InferenceResponse(predictions=predictions)

    # 回退：原有单条路径（内存基线或规则启发）
    predictions = [_predict_one(r.review_id, r.text) for r in req.reviews]
    return InferenceResponse(predictions=predictions)


@router.post("/inference/batch", response_model=InferenceResponse)
async def inference_batch(req: InferenceRequest) -> InferenceResponse:
    """批量推理，返回整体情感 + 属性级情感。

    推理为 CPU/模型密集的同步代码，放入线程池执行，避免阻塞事件循环
    导致训练/推理期间整个服务（含健康检查）无响应。
    """
    return await asyncio.to_thread(_predict_batch_sync, req)


@router.post("/training-runs")
async def create_training_run(req: TrainingRequest) -> dict:
    """训练新模型并返回指标/模型信息；失败以 422 返回可读错误。

    训练耗时可达数分钟，同样放线程池执行，不阻塞事件循环。
    """
    samples = [s.model_dump() for s in req.samples]
    try:
        return await asyncio.to_thread(
            training.run_training,
            samples,
            test_size=req.test_size,
            random_seed=req.random_seed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/training-runs/{run_id}")
async def get_training_run(run_id: str) -> dict:
    record = training.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="训练运行不存在")
    return record


@router.get("/models/current")
async def get_current_model() -> dict:
    model, version = training.get_current()
    if model is None or version is None:
        raise HTTPException(status_code=404, detail="暂无已训练模型")
    return {"model_version": version}


@router.get("/models/{version}")
async def get_model_info(version: str) -> dict:
    record = training.get_model(version)
    if record is None:
        raise HTTPException(status_code=404, detail="模型不存在")
    return record