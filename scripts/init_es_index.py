"""初始化 Elasticsearch 索引。

复用 M2 的 reviews 索引映射（IK 分词），创建名为 settings.reviews_index 的索引。
需先启动 ES（docker compose up -d）并配置 backend/.env 的 ES 连接信息。
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

# 将 backend 目录加入 sys.path，便于以包方式导入 app.*
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("PYTHONUNBUFFERED", "1")


async def _run(force: bool) -> None:
    from app.core.es import (
        close_es,
        ensure_ik_analyzer,
        ensure_reviews_index,
        get_es,
    )

    try:
        await ensure_ik_analyzer()  # 前置校验 IK 分词器，缺插件时给出明确指引
        if force:
            es = get_es()
            await es.indices.delete(index="reviews", ignore_unavailable=True)
        await ensure_reviews_index()
        print("[init_es_index] reviews 索引已就绪。")
    finally:
        await close_es()


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化 ES 索引")
    parser.add_argument(
        "--force", action="store_true", help="若索引已存在则先删除再重建"
    )
    args = parser.parse_args()
    asyncio.run(_run(force=args.force))
    return 0


if __name__ == "__main__":
    sys.exit(main())
