"""E2（P7.5）LLM 蒸馏标签生成：用大模型为评论打高质量语义标签。

对比实验核心：同一批 5k 条评论，用 LLM 读文本打标签（非看星级），
与"弱标签（rating≤2负/3中/≥4正）"训练同一 DistilBERT，对比 F1。

- 走 DashScope OpenAI 兼容端点 + `DASHSCOPE_API_KEY` 环境变量。
- 批量调用（默认 10 条/次），逐批把结果写盘==可中断续跑==。
- `--probe` 仅探测模型名与连通性（1 条），不消耗大量额度。

用法（nlp/ 下）：
  # 探测模型
  .venv\\Scripts\\python.exe -m scripts.llm_label --probe --model qwen-max
  # 正式打标签（首批 5k 条）
  .venv\\Scripts\\python.exe -m scripts.llm_label --model QWEN_MODEL --n 5000 --batch 10
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from scripts.run_experiments import load_samples

# DashScope OpenAI 兼容端点
_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
# 与 run_experiments 一致的全局随机，保证取到同一批 5k 条
SEED = 42
VALID = {"positive", "neutral", "negative"}


def _headers() -> dict:
    key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not key:
        raise RuntimeError("环境变量 DASHSCOPE_API_KEY 未设置")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _sys_prompt() -> str:
    return (
        "你是电商评论情感标注助手。给定一条英文商品评论，判断评论者情绪，"
        "只从这三个标签中选一个返回：positive、neutral、negative。"
        "positive=正面（满意/推荐）；neutral=中性（平淡/无强烈情绪/好坏参半）；"
        "negative=负面（不满/差评/退货意向）。只输出标签本身，不要多余文字。"
        "示例：'Great quality' -> positive；'average, nothing special' -> neutral；"
        "'broke in a week' -> negative。"
    )


def _call(message: str, model: str, *, retry: int = 3, backoff: float = 2.0) -> str:
    """调用一次 chat，返回 assistant 文本；带重试与退避。"""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _sys_prompt()},
            {"role": "user", "content": message},
        ],
        "temperature": 0,
        "max_tokens": 384,
    }
    for attempt in range(retry):
        try:
            resp = requests.post(
                f"{_BASE}/chat/completions", headers=_headers(), json=payload, timeout=60
            )
        except requests.RequestException:
            if attempt == retry - 1:
                raise
            time.sleep(backoff * (attempt + 1))
            continue
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        if resp.status_code in (429, 502, 503, 500):
            if attempt == retry - 1:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            time.sleep(backoff * (2 ** attempt))
            continue
        # 其他错误（404 模型不存在等）直接抛出
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    raise RuntimeError("重试耗尽")


def _parse_batch(text: str, n: int) -> list[str]:
    """尽量从模型输出抽取 n 个标签。"""
    labels: list[str] = []
    low = text.strip().lower()
    # 尝试 JSON 数组
    try:
        start, end = low.find("["), low.rfind("]")
        if start != -1 and end != -1 and end > start:
            arr = json.loads(text[start : end + 1])
            for item in arr:
                if isinstance(item, str):
                    labels.append(item.lower().strip())
    except (json.JSONDecodeError, TypeError, ValueError):
        labels = []
    # 回退：按行拆
    if len(labels) < n:
        for tok in low.replace("\n", " ").replace(",", " ").split():
            tok = tok.strip(" '\"")
            if tok in VALID:
                labels.append(tok)
    return labels[:n]


def label_batch(batch_texts: list[str], model: str, *, batch_split: int = 10) -> list[str]:
    """给一批文本打标签，返回同序标签列表。"""
    out: list[str] = []
    for i in range(0, len(batch_texts), batch_split):
        chunk = batch_texts[i : i + batch_split]
        numbered = "\n".join(
            f"{j + 1}. {t}" for j, t in enumerate(chunk)
        )
        user = (
            "请对下面每条评论分别打情感标签，严格返回 JSON 数组，"
            f"共 {len(chunk)} 个元素，元素为 positive/neutral/negative，顺序与编号一致：\n{numbered}"
        )
        raw = _call(user, model)
        parsed = _parse_batch(raw, len(chunk))
        if len(parsed) < len(chunk):
            # 不足则逐条兜底（更稳但更慢）
            print(f"  [重试] 批解析不足 {len(parsed)}/{len(chunk)}，转逐条")
            for t in chunk:
                single = _call(t, model)
                sp = _parse_batch(single, 1)
                parsed.append(sp[0] if sp else "neutral")
        out.extend(parsed[: len(chunk)])
    return out


def _load_cache(path: Path) -> dict[int, str]:
    if not path.exists():
        return {}
    return {int(k): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def _flush(out_file: Path, cache: dict[int, str]) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(
        json.dumps({str(k): v for k, v in sorted(cache.items())}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def _label_chunk(model: str, split_inner: int, idxs: list[int], texts: list[str]):
    """线程工作单元：为一批文本打标，返回 (idxs, labels)；（失败返回 (idxs, None)）。"""
    try:
        labels = label_batch(texts, model, batch_split=split_inner)
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        print(f"[失败] {idxs[:5]}... : {exc}")
        return idxs, None
    return idxs, labels


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM 蒸馏标签生成")
    parser.add_argument("--model", default="qwen-max")
    parser.add_argument("--data", default="")
    parser.add_argument("--n", type=int, default=5000, help="为该数量的评论打标签")
    parser.add_argument("--batch", type=int, default=10, help="每个工作单元处理的条数")
    parser.add_argument("--split-inner", type=int, default=10, help="单次请求内分批（默认 10 条/次）")
    parser.add_argument("--workers", type=int, default=10, help="并发线程数")
    parser.add_argument("--flush-every", type=int, default=100, help="每新标多少条落盘一次")
    parser.add_argument("--out", default="")
    parser.add_argument("--probe", action="store_true", help="仅探测模型连通性")
    args = parser.parse_args()

    data_path = args.data or str(
        Path(__file__).resolve().parents[2] / "data" / "Appliances.sample30000.jsonl"
    )
    if args.probe:
        print(f"[probe] 探测模型 {args.model} ...")
        try:
            labels = label_batch(["This product is absolutely fantastic, works great!"], args.model, batch_split=1)
            print(f"[probe] 成功，返回: {labels}")
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            print(f"[probe] 失败: {exc}")
        return 0

    samples = load_samples(data_path)
    random.seed(SEED)
    random.shuffle(samples)
    subset = samples[: args.n]
    print(f"[数据] 将用 LLM 为 {len(subset)} 条评论打标签（model={args.model}, batch={args.batch}）")

    out_path = args.out or str(
        Path(__file__).resolve().parents[2]
        / "data" / "llm_labels.json"
    )
    out_file = Path(out_path)
    cache = _load_cache(out_file)
    todo = [i for i in range(len(subset)) if i not in cache]
    print(f"[缓存] 已有 {len(cache)} 条完成，待处理 {len(todo)} 条（workers={args.workers}）")

    out_file.parent.mkdir(parents=True, exist_ok=True)
    if len(todo) == 0:
        _flush(out_file, cache)
        print(f"[完成] 已全部标注，无需处理: {out_file}")
        return 0

    t_lock = threading.Lock()
    total_done = len(cache)
    flush_marker = len(cache)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [
            ex.submit(
                _label_chunk,
                args.model,
                args.split_inner,
                todo[s : s + args.batch],
                [subset[i]["text"] for i in todo[s : s + args.batch]],
            )
            for s in range(0, len(todo), args.batch)
        ]
        n_fail = [0]
        for fut in as_completed(futures):
            idxs, labels = fut.result()
            if labels is None:
                n_fail[0] += 1
                continue
            with t_lock:
                for i, lab in zip(idxs, labels):
                    cache[i] = lab
                total_done = len(cache)
                if total_done - flush_marker >= args.flush_every:
                    _flush(out_file, cache)
                    flush_marker = total_done
                    print(f"[进度] 完成 {total_done}/{len(subset)} 条（失败 {n_fail[0]} 批）")
        _flush(out_file, cache)

    print(f"[完成] 标签已写入: {out_file}（{len(cache)} 条，失败 {n_fail[0]} 批，可重跑补齐）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())