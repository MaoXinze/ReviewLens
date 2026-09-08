"""P7.4 分层推理策略评估：基线 vs 深度 vs cascade。

对一份固定的持出测试集（未被蒸馏模型见过），分别评测：
  - 仅基线（TF-IDF+LR）
  - 仅深度（DistilBERT，取 20k 实验产物）
  - cascade（基线优先，低置信送深度）
并给出分流比例（baseline/deep engine 各承担多少流量）。

测试切割与 run_experiments 使用同一 global shuffle(seed=42)，
取位置在 [20000, 22000) 的样本作为 20k 蒸馏模型从未见过的持出集。

用法（在 nlp/ 下）：
  .venv\\Scripts\\python.exe -m scripts.eval_cascade --deep <模型目录> [--theta 0.90]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sklearn.metrics import accuracy_score, f1_score

from app.services.distilbert_trainer import DistilBertSentimentClassifier
from app.services.sentiment_classifier import TfidfLrSentimentClassifier
from scripts.run_experiments import load_samples

# 与 run_experiments 一致的全局随机
SEED = 42
TRAIN_END = 20000
TEST_END = 22000
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _f1acc(preds: list[str], labels: list[str]) -> tuple[float, float]:
    macro = round(float(f1_score(labels, preds, average="macro")), 6)
    acc = round(float(accuracy_score(labels, preds)), 6)
    return macro, acc


def main() -> int:
    parser = argparse.ArgumentParser(description="分层推理策略评估")
    parser.add_argument(
        "--deep",
        default=str(
            Path(__file__).resolve().parents[1]
            / "app" / "models" / "distilbert_exp_20000"
        ),
        help="20k 蒸馏模型目录",
    )
    parser.add_argument("--data", default="")
    parser.add_argument(
        "--theta",
        default="0.60,0.70,0.80,0.90,0.95",
        help="逗号分隔的置信度阈值列表（默认扫描一组权衡点）",
    )
    args = parser.parse_args()
    thetas = [float(t) for t in args.theta.split(",") if t]

    data_path = args.data or str(
        _PROJECT_ROOT / "data" / "Appliances.sample30000.jsonl"
    )
    samples = load_samples(data_path)
    random.seed(SEED)
    random.shuffle(samples)

    # 训练段沿用 run_experiments 的 0~20000，测试段取 20000~22000（深度模型未见）
    train = samples[:TRAIN_END]
    test = samples[TRAIN_END:TEST_END]
    test_texts = [s["text"] for s in test]
    test_labels = [s["label"] for s in test]
    print(f"[数据] 训练 {len(train)} 条，持出测试 {len(test)} 条")

    # 基线：TF-IDF+LR 在训练段训练
    base_clf = TfidfLrSentimentClassifier()
    base_clf.train(
        [s["text"] for s in train],
        [s["label"] for s in train],
        test_size=0.2,
        random_seed=SEED,
    )
    print("[基线] TF-IDF+LR 训练完成")

    # 深度：加载 20k 蒸馏模型
    deep_clf = DistilBertSentimentClassifier()
    deep_clf.load(args.deep)
    print(f"[深度] 已加载 {Path(args.deep).name}，device={deep_clf.device}")

    base_preds = [p["sentiment"] for p in base_clf.predict(test_texts)]
    deep_preds = [p["sentiment"] for p in deep_clf.predict(test_texts)]
    # 基线样本的置信度（用于分层：低置信 → 送深度）
    base_conf = [p["confidence"] for p in base_clf.predict(test_texts)]

    fm, fa = _f1acc(base_preds, test_labels)
    dm, da = _f1acc(deep_preds, test_labels)

    print("\n=================== 分层推理评估（θ 扫描） ===================")
    print(f"{'θ':<6}{'Macro-F1':<10}{'Accuracy':<10}{'基线流量':<10}{'深度流量':<10}")
    print(f"{'baseline':<6}{fm:<10.6f}{fa:<10.6f}{1.0:<10.2%}{0.0:<10.2%}")
    print(f"{'deep(全量)':<6}{dm:<10.6f}{da:<10.6f}{0.0:<10.2%}{1.0:<10.2%}")

    sweep = []
    for theta in thetas:
        # 低置信索引送深度；其余走基线
        c_preds = list(base_preds)
        for i, conf in enumerate(base_conf):
            if conf < theta:
                c_preds[i] = deep_preds[i]
        cm, ca = _f1acc(c_preds, test_labels)
        deep_count = sum(1 for c in base_conf if c < theta)
        base_ratio = (len(test_texts) - deep_count) / len(test_texts)
        sweep.append(
            {
                "theta": theta,
                "macro_f1": cm,
                "accuracy": ca,
                "baseline_ratio": round(base_ratio, 4),
                "deep_ratio": round(1 - base_ratio, 4),
            }
        )
        print(
            f"{theta:<6.2f}{cm:<10.6f}{ca:<10.6f}"
            f"{base_ratio:<10.2%}{1 - base_ratio:<10.2%}"
        )

    # 写入权衡曲线 JSON

    sweep_path = _PROJECT_ROOT / "docs" / "experiments" / "cascade_tradeoff.json"
    sweep_path.write_text(
        json.dumps(
            {
                "experiment": "M11_cascade_tradeoff",
                "baseline_f1": fm,
                "deep_all_f1": dm,
                "test_samples": len(test_texts),
                "sweep": sweep,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\n[权衡曲线] 已写入: {sweep_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())