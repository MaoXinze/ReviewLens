"""基于受控词表的规则属性抽取（M4 基线）。

从评论文本中识别命中的属性，并基于关键词上下文（前后窗口的正面/负面情感词）
推断该属性的情感极性；无情感词时返回 neutral，规则匹配默认置信度 0.7。
"""
import json
from pathlib import Path

from app.services.preprocessing import clean

# 情感上下文窗口：以关键词为中心，前后各取 N 个字符作为观测窗口
_WINDOW_CHARS = 60

_POSITIVE_WORDS = {
    "good",
    "great",
    "excellent",
    "fast",
    "nice",
    "love",
    "best",
    "perfect",
    "sharp",
    "bright",
    "不错",
    "好",
    "快",
    "清晰",
    "流畅",
    "满意",
    "耐用",
    "值",
    "划算",
    "静音",
    "轻",
    "漂亮",
}

_NEGATIVE_WORDS = {
    "bad",
    "poor",
    "slow",
    "terrible",
    "worst",
    "horrible",
    "slowly",
    "died",
    "broken",
    "issue",
    "problem",
    "cheap",
    "low",
    "糊",
    "差",
    "慢",
    "卡顿",
    "坏",
    "破",
    "故障",
    "发热",
    "烫",
    "贵",
    "响",
    "噪",
    "漏",
}


class RuleBasedAspectExtractor:
    """基于受控词表（aspect_taxonomy.json）的属性抽取器。"""

    def __init__(self, taxonomy_path: str | Path | None = None) -> None:
        self.taxonomy = self._load_taxonomy(taxonomy_path)

    @staticmethod
    def _load_taxonomy(path: str | Path | None) -> dict:
        default = Path(__file__).resolve().parents[1] / "data" / "aspect_taxonomy.json"
        source = Path(path) if path else default
        with source.open(encoding="utf-8") as f:
            data = json.load(f)
        return {name: cfg["keywords"] for name, cfg in data.items()}

    def extract(self, text: str) -> list[dict]:
        """抽取文本命中的属性及其情感。每个属性仅返回一次（按词表顺序）。"""
        if not text:
            return []
        lowered = clean(text)
        aspects: list[dict] = []
        for aspect_name, keywords in self.taxonomy.items():
            for keyword in keywords:
                kw = keyword.lower()
                if kw in lowered:
                    aspects.append(
                        {
                            "aspect": aspect_name,
                            "keyword": keyword,
                            "sentiment": self._infer_sentiment(lowered, kw),
                            "confidence": 0.7,
                        }
                    )
                    break
        return aspects

    @staticmethod
    def _infer_sentiment(text: str, keyword: str) -> str:
        """基于关键词前后窗口内的情感词推断极性；无命中返回 neutral。"""
        idx = text.find(keyword)
        if idx < 0:
            return "neutral"
        start = max(0, idx - _WINDOW_CHARS)
        end = min(len(text), idx + len(keyword) + _WINDOW_CHARS)
        window = text[start:end]

        negative_hits = [w for w in _NEGATIVE_WORDS if w in window]
        positive_hits = [w for w in _POSITIVE_WORDS if w in window]
        if negative_hits:
            return "negative"
        if positive_hits:
            return "positive"
        return "neutral"

    def infer_overall(self, text: str) -> dict:
        """未训练模型时的整体情感兜底：任一负面属性→negative，任一正面→positive，否则 neutral。"""
        aspects = self.extract(text)
        if any(a["sentiment"] == "negative" for a in aspects):
            return {"sentiment": "negative", "confidence": 0.7}
        if any(a["sentiment"] == "positive" for a in aspects):
            return {"sentiment": "positive", "confidence": 0.7}
        return {"sentiment": "neutral", "confidence": 0.7}