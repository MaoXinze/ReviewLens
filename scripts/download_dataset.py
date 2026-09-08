"""下载 Amazon Reviews 2023（UCSD 公开数据集）并按需采样为 JSONL。

数据托管在 McAuley Lab 官方服务器（原 S3 桶已下线）。
脚本按官方直链模板下载品类评论 jsonl.gz，流式解压后随机采样
`--rows` 行写入数据目录，便于本地导入测试与离线开发。

示例：
  python scripts/download_dataset.py --category Electronics --rows 30000
"""
import argparse
import gzip
import hashlib
import json
import random
import sys
import urllib.request
from pathlib import Path

BASE_URL = "https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/raw/review_categories"
DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _reservoir_sample(gz: gzip.GzipFile, rows: int, seed: int) -> list[bytes]:
    """水塘采样：遍历解压流，均匀随机抽取 rows 行。"""
    rng = random.Random(seed)
    reservoir: list[bytes] = []
    for raw in gz:
        line: bytes = raw.strip()
        if not line:
            continue
        if len(reservoir) < rows:
            reservoir.append(line)
        else:
            j = rng.randrange(len(reservoir))
            if j < rows:
                reservoir[j] = line
    return reservoir


def sample_remote(url: str, rows: int, seed: int) -> list[bytes]:
    """流式下载 + 流式解压 + 水塘采样（不把整个文件读入内存）。"""
    with urllib.request.urlopen(url, timeout=300) as resp:
        with gzip.GzipFile(fileobj=resp) as gz:
            return _reservoir_sample(gz, rows, seed)


def sample_local(path: Path, rows: int, seed: int) -> list[bytes]:
    """本地 .jsonl.gz 文件直接采样（配合 curl 断点续传下载使用）。"""
    with path.open("rb") as f:
        with gzip.GzipFile(fileobj=f) as gz:
            return _reservoir_sample(gz, rows, seed)


def main() -> int:
    parser = argparse.ArgumentParser(description="下载 Amazon Reviews 2023 并采样")
    parser.add_argument("--category", default="Appliances", help="品类")
    parser.add_argument("--rows", type=int, default=1000, help="采样行数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--local-file",
        type=Path,
        default=None,
        help="本地已下载的 .jsonl.gz 文件路径（离线模式，跳过网络下载）",
    )
    args = parser.parse_args()

    if args.local_file is not None:
        gz_path = args.local_file
        if not gz_path.exists():
            print(f"[download_dataset] 文件不存在: {gz_path}", file=sys.stderr)
            return 1
        print(f"[download_dataset] 使用本地文件 {gz_path}", flush=True)
        reservoir = sample_local(gz_path, args.rows, args.seed)
    else:
        url = f"{BASE_URL}/{args.category}.jsonl.gz"
        print(f"[download_dataset] 下载 {url}", flush=True)
        reservoir = sample_remote(url, args.rows, args.seed)

    args.data_dir.mkdir(parents=True, exist_ok=True)
    out = args.data_dir / f"{args.category}.sample{args.rows}.jsonl"

    # 原始 Amazon 数据没有 review_id；基于内容生成确定性 ID（导入引擎必需字段）
    lines: list[bytes] = []
    for raw in reservoir:
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        digest = hashlib.sha1(
            f"{obj.get('user_id', '')}|{obj.get('asin', '')}|"
            f"{obj.get('timestamp', '')}|{args.category}".encode()
        ).hexdigest()[:16]
        obj["review_id"] = f"{args.category[:4].lower()}-{digest}"
        lines.append(json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    out.write_bytes(b"\n".join(lines) + b"\n")

    print(f"[download_dataset] 已写入 {out}（{len(lines)} 行）", flush=True)
    print(f"[download_dataset] sha256={_sha(out)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())