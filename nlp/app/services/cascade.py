"""分层推理策略（P7.4 / M11 第三层架构落地）。

企业级 cascade inference：多数评论用低延迟可解释的 TF-IDF+LR 基线，
只有基线置信度低于阈值（不确定样本）才送 DistilBERT 深度模型复核，
从而在精度与成本/时延之间取平衡。

```
新评论 → 基线预测
  ├── confidence ≥ θ_high → 直接采用（约 70-80% 流量）
  └── confidence <  θ_high → 送 DistilBERT 复核（约 20-30% 流量）
```

同类模型统一对外接口 train/predict，因此这里可透明编排两类模型。
"""
from __future__ import annotations


class CascadeInference:
    """基线优先、深度复核的分层推理器。

    Parameters
    ----------
    baseline: 提供 predict(texts) -> list[{sentiment, confidence}]
    deep:     提供 predict(texts) -> list[{sentiment, confidence}]
    theta_high: 置信度阈值，基线 ≥ 该值直接采用，否则送深度模型
    """

    def __init__(self, baseline, deep, theta_high: float = 0.90) -> None:
        if not (0.0 < theta_high < 1.0):
            raise ValueError("theta_high 需在 (0,1) 区间")
        self.baseline = baseline
        self.deep = deep
        self.theta_high = theta_high

    def predict(self, texts: list[str]) -> dict:
        """执行分层推理。

        Returns
        -------
        {
          "results": [{"index", "sentiment", "confidence", "route"}],
          "stats": {
            "total", "baseline_count", "deep_count",
            "baseline_ratio", "deep_ratio",
          },
        }
        """
        if not texts:
            return {"results": [], "stats": self._stats(0, 0)}

        base_preds = self.baseline.predict(texts)
        # 需要送深度的索引与对应文本
        deep_idx = [i for i, p in enumerate(base_preds) if p["confidence"] < self.theta_high]
        deep_preds: dict[int, dict] = {}
        if deep_idx:
            deep_texts = [texts[i] for i in deep_idx]
            deep_out = self.deep.predict(deep_texts)
            deep_preds = {idx: p for idx, p in zip(deep_idx, deep_out)}

        results = []
        for i, p in enumerate(base_preds):
            if i in deep_preds:
                dp = deep_preds[i]
                results.append(
                    {
                        "index": i,
                        "sentiment": dp["sentiment"],
                        "confidence": dp["confidence"],
                        "route": "deep",
                    }
                )
            else:
                results.append(
                    {
                        "index": i,
                        "sentiment": p["sentiment"],
                        "confidence": p["confidence"],
                        "route": "baseline",
                    }
                )

        stats = self._stats(len(texts), len(results) - len(deep_idx))
        return {"results": results, "stats": stats}

    @staticmethod
    def _stats(total: int, baseline_count: int) -> dict:
        base_ratio = round(baseline_count / total, 4) if total else 0.0
        return {
            "total": total,
            "baseline_count": baseline_count,
            "deep_count": total - baseline_count,
            "baseline_ratio": base_ratio,
            "deep_ratio": round(1.0 - base_ratio, 4) if total else 0.0,
        }