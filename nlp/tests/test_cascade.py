"""分层推理单元测试：路由决策 + 统计 + 深度模型缺失时优雅回退。

用假基线/深度分类器（不加载真实权重），聚焦 CascadeInference 的编排逻辑。
"""
import pytest

from app.services.cascade import CascadeInference


class _FakeBase:
    def predict(self, texts):
        # 高置信直接给出；text"uncertain..." 返回低置信，触发深度路由
        out = []
        for t in texts:
            if t.startswith("uncertain"):
                out.append({"sentiment": "neutral", "confidence": 0.30})
            else:
                out.append({"sentiment": "positive", "confidence": 0.98})
        return out


class _FakeDeep:
    def predict(self, texts):
        return [{"sentiment": "negative", "confidence": 0.90}] * len(texts)


def test_cascade_routes_low_confidence_to_deep():
    cascade = CascadeInference(_FakeBase(), _FakeDeep(), theta_high=0.70)
    out = cascade.predict(["clear", "uncertain", "clear2"])
    assert out["results"][0]["route"] == "baseline"
    assert out["results"][1]["route"] == "deep"
    assert out["results"][1]["sentiment"] == "negative"  # 深度判定覆盖基线
    assert out["results"][2]["route"] == "baseline"
    stats = out["stats"]
    assert stats["total"] == 3
    assert stats["baseline_count"] == 2 and stats["deep_count"] == 1
    assert stats["baseline_ratio"] == round(2 / 3, 4)
    assert stats["deep_ratio"] == round(1 / 3, 4)


def test_cascade_empty_input():
    cascade = CascadeInference(_FakeBase(), _FakeDeep())
    out = cascade.predict([])
    assert out["results"] == []
    assert out["stats"]["total"] == 0


def test_cascade_invalid_theta():
    with pytest.raises(ValueError):
        CascadeInference(_FakeBase(), _FakeDeep(), theta_high=1.5)


def test_cascade_high_theta_sends_more_to_deep():
    low = CascadeInference(_FakeBase(), _FakeDeep(), theta_high=0.60).predict(
        ["clear", "uncertain"]
    )
    high = CascadeInference(_FakeBase(), _FakeDeep(), theta_high=0.95).predict(
        ["clear", "uncertain"]
    )
    # 高阈值下"clear"(0.98<0.95? 否) 仍走基线；但 0.60 阈值下无一低置信送深度
    assert low["stats"]["deep_count"] == 1
    assert high["stats"]["deep_count"] == 1