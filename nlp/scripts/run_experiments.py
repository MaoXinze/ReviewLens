"""M11 样本量敏感性实验驱动脚本（P7.3）。

对不同样本量（1k / 5k / 2w / 5w，超出数据按全量封顶）分别用 DistilBERT
微调，产出 Macro-F1/Accuracy/训练耗时/设备，写入 JSON 报告并打印曲线数据。

用法：
    uv run python -m scripts.run_experiments --data <样本jsonl> --sizes 1000,5000,20000,50000
    （在 nlp/ 目录下执行；默认读取 data 下 Appliances.sample30000.jsonl）
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

# 保证可被 `python -m scripts.run_experiments` 调用
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.services.distilbert_trainer import DistilBertSentimentClassifier

# 项目根（nlp/scripts/run_experiments.py → parents[2] = sentiment-plus）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _weak_label(rating: float) -> str | None:
    """评分弱标签：1-2 负 / 3 中性 / 4-5 正。"""
    if rating <= 2.0:
        return "negative"
    if rating == 3.0:
        return "neutral"
    return "positive"


def load_samples(data_path: str) -> list[dict]:
    samples = []
    with open(data_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            text = (rec.get("text") or "").strip()
            if not text:
                continue
            label = _weak_label(float(rec.get("rating", 0.0)))
            if label is None:
                continue
            samples.append({"text": text, "label": label})
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description="DistilBERT 样本量敏感性实验")
    parser.add_argument("--data", default="", help="样本 JSONL 路径（默认取项目 data 下 3 万条采样）")
    parser.add_argument("--sizes", default="1000,5000,20000,50000")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="")
    parser.add_argument("--max-samples", type=int, default=0, help="全量数据截断（0=全用）")
    args = parser.parse_args()

    data_path = args.data or str(_PROJECT_ROOT / "data" / "Appliances.sample30000.jsonl")
    if not Path(data_path).exists():
        print(f"[错误] 数据文件不存在: {data_path}")
        return 1

    samples = load_samples(data_path)
    print(f"[加载] {len(samples)} 条样本，数据源: {data_path}")
    if args.max_samples and len(samples) > args.max_samples:
        samples = samples[: args.max_samples]

    random.seed(args.seed)
    # 固定全局乱序，各样本量取同一前缀 → 干净的单调性曲线
    random.shuffle(samples)

    sizes = [int(s) for s in args.sizes.split(",")]
    results = []
    for size in sizes:
        n = min(size, len(samples))
        subset = samples[:n]
        print(f"\n===== 实验 size={size}（实际 {n} 条）=====")
        clf = DistilBertSentimentClassifier(
            epochs=args.epochs, batch_size=args.batch_size
        )
        texts = [s["text"] for s in subset]
        labels = [s["label"] for s in subset]
        metrics = clf.train(texts, labels, random_seed=args.seed)

        model_path = Path(settings.model_dir) / f"distilbert_exp_{n}"
        clf.save(str(model_path))
        results.append(
            {
                "size": size,
                "actual_samples": n,
                "macro_f1": metrics["macro_f1"],
                "accuracy": metrics["accuracy"],
                "train_seconds": metrics["train_seconds"],
                "device": metrics["device"],
                "train_samples": metrics["train_samples"],
                "test_samples": metrics["test_samples"],
                "per_class": metrics["per_class"],
                "model_path": str(model_path),
                "trained_at": datetime.now(UTC).isoformat(),
            }
        )
        print(
            f"[结果] size={size}: Macro-F1={metrics['macro_f1']:.4f} "
            f"Acc={metrics['accuracy']:.4f} 训练耗时={metrics['train_seconds']:.1f}s "
            f"({metrics['device']})"
        )

    report = {
        "experiment": "M11_distilbert_sample_size",
        "base_model": "distilbert-base-uncased",
        "seed": args.seed,
        "weak_label_rule": "rating<=2 negative, ==3 neutral, >=4 positive",
        "results": results,
        "created_at": datetime.now(UTC).isoformat(),
    }
    out_path = args.out or str(
        _PROJECT_ROOT / "docs" / "experiments" / "distilbert_sample_size.json"
    )
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n[报告] 已写入: {out_file}")

    print("\n===== 样本量-性能曲线 =====")
    print("size\tactual\tmacro_f1\tacc\ttrain_s")
    for r in results:
        print(
            f"{r['size']}\t{r['actual_samples']}\t{r['macro_f1']:.4f}\t"
            f"{r['accuracy']:.4f}\t{r['train_seconds']:.1f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())