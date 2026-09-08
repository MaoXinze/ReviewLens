"""从已训练好的 distilbert_exp_* 的 meta.json 汇总为实验报告 JSON。

不必重训即可生成 docs/experiments/distilbert_sample_size.json。
用法（nlp/ 下）：　.venv\\Scripts\\python.exe -m scripts.collect_experiment_report
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    model_dir = Path(settings.model_dir)
    results = []
    # 按 distilbert_exp_<n> 目录自适应收集（n = 实际样本量）
    exp_dirs = sorted(
        (d for d in model_dir.glob("distilbert_exp_*") if d.is_dir()),
        key=lambda d: int(d.name.split("_")[-1]),
    )
    for d in exp_dirs:
        meta_path = d / "meta.json"
        if not meta_path.exists():
            print(f"[跳过] {meta_path.name} 不存在")
            continue
        size = int(d.name.split("_")[-1])
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        results.append(
            {
                "size": size,
                "actual_samples": meta.get("train_samples", 0) + meta.get("test_samples", 0),
                "macro_f1": meta["macro_f1"],
                "accuracy": meta["accuracy"],
                "train_seconds": meta["train_seconds"],
                "device": meta["device"],
                "train_samples": meta.get("train_samples"),
                "test_samples": meta.get("test_samples"),
                "per_class": meta.get("per_class"),
                "model_path": str(d),
                "trained_at": meta.get("saved_at"),
            }
        )
    report = {
        "experiment": "M11_distilbert_sample_size",
        "base_model": "distilbert-base-uncased",
        "seed": 42,
        "weak_label_rule": "rating<=2 negative, ==3 neutral, >=4 positive",
        "results": results,
        "created_at": datetime.now(UTC).isoformat(),
    }
    out_file = PROJECT_ROOT / "docs" / "experiments" / "distilbert_sample_size.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[报告] 已写入: {out_file} ({len(results)} 组)")
    for r in results:
        print(
            f"size={r['size']:>6} actual={r['actual_samples']:>6} "
            f"f1={r['macro_f1']:.4f} acc={r['accuracy']:.4f} "
            f"train_s={r['train_seconds']:.1f} ({r['device']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())