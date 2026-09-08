"""评论行校验与规范化（纯函数，无 IO，便于单元测试）。

M2 校验规则：
  必填 review_id/product_id/review_text/reviewed_at；
  review_id 同一数据集内唯一；review_text 1~5000；
  reviewed_at 可解析为时间戳；rating 存在时须为 1~5 整数；
  检测语言（en/zh/mixed）。
"""
import hashlib
import re
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings

# 规范化字段 -> 源数据字段名（默认适配 Amazon Reviews 2023 字段）
DEFAULT_FIELD_MAPPING: dict[str, str] = {
    "review_id": "review_id",
    "product_id": "asin",
    "product_group_id": "parent_asin",
    "review_title": "title",
    "review_text": "text",
    "reviewed_at": "timestamp",
    "reviewer_id": "user_id",
    "helpful_votes": "helpful_vote",
    "verified_purchase": "verified_purchase",
    "rating": "rating",
}

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def detect_language(text: str) -> str:
    """启发式语言识别：无中文字符->en；中文占比>=40%->zh；混排->mixed。"""
    if not text:
        return "en"
    cjk = len(_CJK_RE.findall(text))
    if cjk == 0:
        return "en"
    ratio = cjk / max(len(text), 1)
    if ratio >= 0.4:
        return "zh"
    return "mixed"


def _coerce_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_timestamp(value: Any) -> datetime | None:
    """解析 reviewed_at：支持 ISO 字符串或 unix 时间戳（秒/毫秒）。"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1_000_000_000_000:
            ts /= 1000  # 毫秒
        return datetime.fromtimestamp(ts, tz=UTC)
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return _coerce_timestamp(int(text))
        try:
            cleaned = text.replace("Z", "+00:00")
            return datetime.fromisoformat(cleaned)
        except ValueError:
            return None
    return None


def _coerce_rating(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        rating = int(value)
    except (TypeError, ValueError):
        return None
    return rating if 1 <= rating <= 5 else None


def validate_row(
    row: dict[str, Any], mapping: dict[str, str], seen_ids: set[str]
) -> tuple[dict | None, list[str]]:
    """校验并规范化单条评论，返回 (normalized, errors)。errors 非空表示该行被拒绝。"""
    errors: list[str] = []
    max_len = settings.max_review_text_length

    def field(canonical: str) -> Any:
        src = mapping.get(canonical)
        return row.get(src) if src else None

    review_id = field("review_id")
    product_id = field("product_id")
    review_text = field("review_text")
    reviewed_at = field("reviewed_at")
    rating = field("rating")

    if not review_id:
        errors.append("missing_review_id")
    elif review_id in seen_ids:
        errors.append("duplicate_id")
    if not product_id:
        errors.append("missing_product_id")
    if not review_text:
        errors.append("empty_text")
    elif len(review_text) > max_len:
        errors.append("too_long")

    reviewed_dt = _coerce_timestamp(reviewed_at)
    if reviewed_dt is None:
        errors.append("invalid_timestamp")

    rating_val = _coerce_rating(rating)
    if rating is not None and rating_val is None:
        errors.append("invalid_rating")

    if errors:
        return None, errors

    seen_ids.add(review_id)
    helpful = field("helpful_votes")
    vp = field("verified_purchase")
    normalized = {
        "review_id": str(review_id)[:200],
        "product_id": str(product_id)[:100],
        "product_group_id": (
            str(field("product_group_id"))[:100] if field("product_group_id") else None
        ),
        "review_title": str(field("review_title")) if field("review_title") else None,
        "review_text": str(review_text),
        "rating": rating_val,
        "reviewed_at": reviewed_dt,
        "reviewer_id": (
            str(field("reviewer_id"))[:200] if field("reviewer_id") else None
        ),
        "helpful_votes": _coerce_int(helpful) if helpful is not None else 0,
        "verified_purchase": bool(vp) if vp is not None else False,
        "language": detect_language(str(review_text)),
    }
    return normalized, []


def generate_dataset_version(file_content: bytes) -> str:
    """由文件内容生成稳定版本号 ds-{sha256前8位}。"""
    sha = hashlib.sha256(file_content).hexdigest()[:8]
    return f"ds-{sha}"
