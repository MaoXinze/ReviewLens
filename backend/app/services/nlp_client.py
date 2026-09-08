"""NLP 服务 HTTP 客户端（M4）。

backend 通过本模块调用独立 NLP 服务（端口 8100）的推理/训练接口。
连接失败或非 2xx 时抛出 NLPUnavailable / NLPRemoteError，由调用方转为 HTTP 错误。
"""
import httpx

from app.core.config import settings


class NLPUnavailable(Exception):
    """NLP 服务不可达。"""


class NLPRemoteError(Exception):
    """NLP 服务返回错误。"""


def _base_url() -> str:
    return settings.nlp_base_url.rstrip("/")


async def infer_batch(
    reviews: list[dict], model_version: str | None = None
) -> list[dict]:
    """批量推理：reviews 为 [{review_id, text}]，返回 NLP 预测结果列表。"""
    payload: dict = {"reviews": reviews}
    if model_version:
        payload["model_version"] = model_version
    data = await _request(
        "POST", "/api/v1/inference/batch", payload, settings.nlp_inference_timeout
    )
    return data.get("predictions", [])


async def train_model(
    samples: list[dict],
    *,
    test_size: float | None = None,
    random_seed: int | None = None,
) -> dict:
    """训练新模型，返回指标/模型信息（NLP 服务侧同步完成）。"""
    payload: dict = {"samples": samples}
    if test_size is not None:
        payload["test_size"] = test_size
    if random_seed is not None:
        payload["random_seed"] = random_seed
    return await _request(
        "POST", "/api/v1/training-runs", payload, settings.nlp_training_timeout
    )


async def get_current_model() -> dict | None:
    """查询 NLP 服务当前生产模型。无模型时返回 None。"""
    return await _request(
        "GET", "/api/v1/models/current", None, settings.nlp_inference_timeout
    )


async def _request(
    method: str, path: str, payload: dict | None, timeout: float
) -> dict:
    url = f"{_base_url()}{path}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.request(method, url, json=payload)
        except httpx.HTTPError as exc:
            raise NLPUnavailable(f"NLP 服务不可达: {exc}") from None
    if resp.status_code in (200, 201):
        return resp.json()
    if resp.status_code == 404 and method == "GET" and path == "/api/v1/models/current":
        return None
    raise NLPRemoteError(f"NLP 服务返回 {resp.status_code}: {resp.text[:200]}")
