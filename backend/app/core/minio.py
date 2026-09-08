"""MinIO（S3 兼容）对象存储客户端。

Minio 官方客户端为同步 API，本模块用 asyncio.to_thread 封装成异步，
使 FastAPI/ARQ 协程中可直接 await，不阻塞事件循环。
"""
import asyncio
from collections.abc import AsyncIterator
from io import BytesIO

from minio import Minio

from app.core.config import settings

_client: Minio | None = None

# 流式读取的默认块大小（256KB：内存占用与 to_thread 调用开销的平衡）
CHUNK_SIZE = 256 * 1024


def get_minio() -> Minio:
    """返回（并按需创建）全局 MinIO 客户端。"""
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    return _client


def _bucket_sync():
    client = get_minio()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


async def ensure_bucket() -> None:
    """确保默认桶存在（幂等）。"""
    await asyncio.to_thread(_bucket_sync)


async def upload_bytes(object_name: str, data: bytes) -> None:
    """上传字节内容到 MinIO，若桶不存在则自动创建。"""
    await ensure_bucket()
    client = get_minio()
    await asyncio.to_thread(
        client.put_object,
        settings.minio_bucket,
        object_name,
        BytesIO(data),
        len(data),
    )


async def read_bytes(object_name: str) -> bytes:
    """从 MinIO 读取完整对象内容（仅小对象使用；大对象用 iter_object_chunks）。"""
    client = get_minio()
    response = await asyncio.to_thread(
        client.get_object, settings.minio_bucket, object_name
    )
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


async def iter_object_chunks(
    object_name: str, chunk_size: int = CHUNK_SIZE
) -> AsyncIterator[bytes]:
    """流式读取 MinIO 对象，逐块产出字节，不整段载入内存。

    单读连接顺序消费；用完后关闭连接并归还连接池。
    """
    client = get_minio()
    response = await asyncio.to_thread(
        client.get_object, settings.minio_bucket, object_name
    )
    try:
        while True:
            chunk = await asyncio.to_thread(response.read, chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        await asyncio.to_thread(response.close)
        await asyncio.to_thread(response.release_conn)
