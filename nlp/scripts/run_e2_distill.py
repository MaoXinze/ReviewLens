"""E2（P7.5）LLM 蒸馏标签对照训练：弱标签 vs LLM 标签，同一 DistilBERT、同一固定切分。

隔离「标签来源」这一变量：
  - 同样 5k 条评论（全局 shuffle[0:5000]，seed=42）
  - 固定持出测试 = 全局 shuffle[4000:5000]（1k 条，两路均只在 [0:4000] 训练）
  - 一路用弱标签（rating）、一路用 LLM 标签（read 文本语义），训练同一 DistilBERT
  - 在同一持出测试上对比 Macro-F1 / Accuracy，并给出标签分歧率

用法（nlp/ 下）：
  .venv\\Scripts\\python.exe -m scripts.run_e2_distill --n 5000
  （LLM 标签读取 data/llm_labels.json，由 scripts.llm_label 生成）
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.distilbert_trainer import DistilBertSentimentClassifier
from scripts.run_experiments import load_samples

SEED = 42
TRAIN_END = 4000
TEST_END = 5000
VALID = {"positive", "neutral", "negative"}
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="E2 LLM 蒸馏标签对照训练")
    parser.add_argument("--n", type=int, default=5000)
    parser.add_argument("--data", default="")
    parser.add_argument("--labels", default="")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--tag", default="", help="模型/报告命名标签，默认取标签文件 basename，避免不同标签源互相覆盖权重")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    data_path = args.data or str(
        _PROJECT_ROOT / "data" / "Appliances.sample30000.jsonl"
    )
    labels_path = args.labels or str(_PROJECT_ROOT / "data" / "llm_labels.json")
    # 用标签源唯一化产物命名，保证多模型复跑不互相覆盖权重
    tag = args.tag or Path(labels_path).stem

    samples = load_samples(data_path)
    random.seed(SEED)
    random.shuffle(samples)
    subset = samples[: args.n]
    texts = [s["text"] for s in subset]

    # 弱标签（load_samples 已按评分折算：rating≤2 负 / 3 中 / ≥4 正）
    weak = [s["label"] for s in subset]
    # LLM 标签
    if not Path(labels_path).exists():
        print(f"[错误] LLM 标签文件不存在: {labels_path}")
        return 1
    raw = json.loads(Path(labels_path).read_text(encoding="utf-8"))
    llm = []
    for i in range(len(subset)):
        lab = raw.get(str(i), "")
        llm.append(lab if lab in VALID else "neutral")

    # 固定切分：train [0,TRAIN_END)，test [TRAIN_END,TEST_END)
    train_idx = list(range(TRAIN_END))
    test_idx = list(range(TRAIN_END, TEST_END))

    # 标签分歧率
    disagree = sum(1 for w, l in zip(weak, llm) if w != l)
    print(f"[数据] n={args.n}，固定切分 train={TRAIN_END}/test={TEST_END - TRAIN_END}")
    print(f"[标签] 弱标签与 LLM 标签分歧率: {disagree}/{args.n} = {disagree / args.n:.2%}")

    def train_and_eval(source: str, labels: list[str]) -> dict:
        clf = DistilBertSentimentClassifier(epochs=args.epochs)
        m = clf.train(
            texts, labels, train_idx=train_idx, test_idx=test_idx, random_seed=SEED
        )
        model_path = (
            _PROJECT_ROOT / "nlp" / "app" / "models" / f"distilbert_e2_{tag}_{source}"
        )
        clf.save(str(model_path))
        print(
            f"[{source}] Macro-F1={m['macro_f1']:.4f} Acc={m['accuracy']:.4f} "
            f"train_s={m['train_seconds']:.1f}s"
        )
        return {
            "source": source,
            "macro_f1": m["macro_f1"],
            "accuracy": m["accuracy"],
            "train_seconds": m["train_seconds"],
            "device": m["device"],
            "train_samples": m["train_samples"],
            "test_samples": m["test_samples"],
            "model_path": str(model_path),
        }

    res_weak = train_and_eval("weak", weak)
    res_llm = train_and_eval("llm", llm)

    report = {
        "experiment": "M11_e2_llm_distill",
        "model": "distilbert-base-uncased",
        "n": args.n,
        "train_idx": [0, TRAIN_END],
        "test_idx": [TRAIN_END, TEST_END],
        "label_disagreement_rate": round(disagree / args.n, 4),
        "results": [res_weak, res_llm],
        "created_at": datetime.now(UTC).isoformat(),
    }
    out_path = args.out or str(
        _PROJECT_ROOT / "docs" / "experiments" / "e2_llm_distill.json"
    )
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n[报告] 已写入: {out_file}")

    # 结论打印
    lift = res_llm["macro_f1"] - res_weak["macro_f1"]
    print("\n========== E2 结论 ==========")
    print(
        f"弱标签 F1={res_weak['macro_f1']:.4f} | LLM标签 F1={res_llm['macro_f1']:.4f} "
        f"| 差值={lift:+.4f}"
    )
    if abs(lift) < 0.01:
        print("标签来源对 F1 无明显影响（弱标签够用）。")
    elif lift > 0:
        print("LLM 高质量标签显著提升 F1，说明弱标签是主要瓶颈。")
    else:
        print("LLM 标签反而更低（弱标签已够用 / LLM 引入噪声）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())