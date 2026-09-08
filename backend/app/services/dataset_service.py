"""数据导入编排：上传、幂等去重、入队；并供 ARQ Worker 使用的解析逻辑。

流程：
  submit_import(API侧): 读文件→计算版本→幂等检查→存 MinIO→建记录→入队
  run_import（Worker侧): 读 MinIO → 解析校验 → 批量写 PG → 批量写 ES → 生成质量报告
"""
import codecs
import csv
import hashlib
import io
import json
import zlib
from collections.abc import Iterable, Iterator
from uuid import uuid4

from arq.connections import RedisSettings, create_pool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.minio import upload_bytes
from app.models.dataset import Dataset
from app.services.validation import (
    DEFAULT_FIELD_MAPPING,
    generate_dataset_version,
    validate_row,
)


async def enqueue_import(dataset_version: str) -> None:
    """将导入任务入队（ARQ Redis 队列）。"""
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    redis = await create_pool(redis_settings)
    try:
        await redis.enqueue_job("run_import", dataset_version)
    finally:
        await redis.aclose()


class IncrementalLineSplitter:
    """增量行切分器：逐块 feed 字节，产出完整行；处理跨块断行、BOM 与可选 gzip。

    JSONL 行内不含换行（json.loads 排除字面换行），按 \n 切分安全；
    CSV 字段可含引号内换行，不能走此路径（见 parse_rows 的 CSV 分支）。
    """

    def __init__(self, *, gzip_encoded: bool = False) -> None:
        self._deco = zlib.decompressobj(16 + zlib.MAX_WBITS) if gzip_encoded else None
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._buf = ""
        self._first = True

    def feed(self, chunk: bytes) -> list[str]:
        """喂入一个字节块，返回其中已完整的行（可能为空）。"""
        data = self._deco.decompress(chunk) if self._deco is not None else chunk
        if not data:
            return []
        text = self._decoder.decode(data)
        if self._first:
            text = text.lstrip("\ufeff")
            self._first = False
        if not text:
            return []
        lines = (self._buf + text).split("\n")
        self._buf = lines.pop()
        return lines

    def flush(self) -> list[str]:
        """流结束时调用，返回尾部残余行（若有）。"""
        tail = self._decoder.decode(b"", final=True)
        rest = self._buf + tail
        self._buf = ""
        return [rest] if rest.strip() else []


def _iter_lines(
    chunks: Iterable[bytes], *, gzip_encoded: bool = False
) -> Iterator[str]:
    """把字节块流转成行迭代器（IncrementalLineSplitter 的生成器封装）。"""
    splitter = IncrementalLineSplitter(gzip_encoded=gzip_encoded)
    for chunk in chunks:
        yield from splitter.feed(chunk)
    yield from splitter.flush()


def parse_jsonl_line(
    line: str, mapping: dict[str, str], seen: set[str]
) -> tuple[dict | None, list[str]]:
    """解析单条 JSONL 并校验，返回 (normalized, errors)；JSON 语法错误抛 ValueError。"""
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        raise ValueError("文件包含无法解析的 JSON 行") from None
    return validate_row(row, mapping, seen)


def stream_parse_jsonl_rows(
    chunks: Iterable[bytes], field_mapping: dict | None = None
) -> Iterator[tuple[dict | None, list[str]]]:
    """流式解析 JSONL 字节块，逐行产出 (normalized, errors)。

    normalized 为 None 且 errors 非空表示该行被拒绝；与 parse_rows 的
    JSONL 语义一致（坏 JSON 行抛 ValueError）。
    """
    mapping = {**DEFAULT_FIELD_MAPPING, **(field_mapping or {})}
    seen: set[str] = set()
    for line in _iter_lines(chunks):
        stripped = line.strip()
        if not stripped:
            continue
        yield parse_jsonl_line(stripped, mapping, seen)


def parse_rows(
    content: bytes, field_mapping: dict | None = None
) -> tuple[list[dict], dict[str, int]]:
    """解析 JSONL/CSV 并逐行校验，返回 (valid_rows, rejection_reasons)。

    valid_rows 为已规范化的评论 dict（reviewed_at 为 datetime）。
    JSONL 走流式切分；CSV 因字段可含引号内换行，需整体解析。
    """
    mapping = {**DEFAULT_FIELD_MAPPING, **(field_mapping or {})}
    valid: list[dict] = []
    reasons: dict[str, int] = {}

    def add_reason(reason: str) -> None:
        reasons[reason] = reasons.get(reason, 0) + 1

    stripped = content.decode("utf-8", errors="replace").lstrip("\ufeff").lstrip()
    if not stripped:
        return valid, reasons

    if stripped.startswith("{"):
        stream = stream_parse_jsonl_rows(iter([content]), field_mapping)
        for normalized, errors in stream:
            if errors:
                for err in errors:
                    add_reason(err)
            else:
                valid.append(normalized)
        return valid, reasons

    seen: set[str] = set()
    reader = csv.DictReader(io.StringIO(stripped))
    if not reader.fieldnames:
        raise ValueError("CSV 文件缺少表头")
    for row in reader:
        normalized, errors = validate_row(row, mapping, seen)
        if errors:
            for err in errors:
                add_reason(err)
            continue
        valid.append(normalized)
    return valid, reasons


async def submit_import(
    db: AsyncSession,
    *,
    content: bytes,
    filename: str,
    field_mapping: dict | None,
    created_by: str | None,
) -> dict:
    """执行一次导入提交：幂等去重 → 存 MinIO → 建记录 → 入队。"""
    version = generate_dataset_version(content)
    existing = (
        await db.execute(select(Dataset).where(Dataset.dataset_version == version))
    ).scalar_one_or_none()
    if existing is not None:
        return {
            "status": "queued",
            "message": "该文件已导入过，直接复用",
            "dataset_version": existing.dataset_version,
            "reused": True,
        }

    storage_path = f"datasets/{version}/{filename}"
    await upload_bytes(storage_path, content)

    dataset = Dataset(
        id=str(uuid4()),
        dataset_version=version,
        source_filename=filename,
        file_sha256=hashlib.sha256(content).hexdigest(),
        storage_path=storage_path,
        field_mapping=field_mapping or {},
        status="importing",
        created_by=created_by,
    )
    db.add(dataset)
    await db.commit()

    await enqueue_import(version)
    return {
        "status": "queued",
        "message": "导入任务已提交",
        "dataset_version": version,
        "reused": False,
    }
