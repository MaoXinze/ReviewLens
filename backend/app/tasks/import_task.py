"""ARQ 异步导入任务：流式读 MinIO → 逐行校验 → 分批写 PG/ES → 质量报告。

作为 worker 的独立函数运行（见 app/worker.py）。JSONL（含 .gz）走真正的
流式路径（行级增量解析，内存占用与文件大小解耦）；CSV 因字段可含引号内
换行，回退为整段解析。任何异常都将数据集标记为 failed 并记录 error_message，
满足验收标准 6。
"""
from uuid import uuid4

from sqlalchemy import select

from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.es import bulk_index_reviews, ensure_reviews_index
from app.core.minio import iter_object_chunks, read_bytes
from app.models.dataset import Dataset
from app.models.review import Review
from app.services.dataset_service import (
    DEFAULT_FIELD_MAPPING,
    IncrementalLineSplitter,
    parse_jsonl_line,
    parse_rows,
)


def _to_es_doc(row: dict, dataset_version: str) -> dict:
    """规范化 dict 转 ES 文档（reviewed_at 序列化为 ISO 字符串）。"""
    doc = dict(row)
    doc["reviewed_at"] = row["reviewed_at"].isoformat()
    doc["dataset_version"] = dataset_version
    return doc


def _to_orm(row: dict, dataset_version: str) -> Review:
    return Review(
        id=str(uuid4()),
        dataset_version=dataset_version,
        review_id=row["review_id"],
        product_id=row["product_id"],
        product_group_id=row.get("product_group_id"),
        review_title=row.get("review_title"),
        review_text=row["review_text"],
        rating=row.get("rating"),
        reviewed_at=row["reviewed_at"],
        reviewer_id=row.get("reviewer_id"),
        helpful_votes=row.get("helpful_votes", 0),
        verified_purchase=row.get("verified_purchase", False),
        language=row.get("language", "en"),
    )


class _StreamingImporter:
    """流式导入的有状态游标：去重、拒绝计数与「PG 提交 → ES 索引」分批落库。"""

    def __init__(self, db, dataset: Dataset) -> None:
        self._db = db
        self._dataset = dataset
        self.mapping = {**DEFAULT_FIELD_MAPPING, **(dataset.field_mapping or {})}
        self.seen: set[str] = set()
        self.reasons: dict[str, int] = {}
        self.imported = 0
        self.rejected = 0
        self._orm_batch: list[Review] = []
        self._row_batch: list[dict] = []

    def add_reasons(self, errors: list[str]) -> None:
        self.rejected += 1
        for err in errors:
            self.reasons[err] = self.reasons.get(err, 0) + 1

    def add_row(self, normalized: dict) -> None:
        self._orm_batch.append(_to_orm(normalized, self._dataset.dataset_version))
        self._row_batch.append(normalized)

    @property
    def full(self) -> bool:
        return len(self._orm_batch) >= settings.import_batch_size

    async def flush(self) -> None:
        """提交当前批次：先 PG commit，后 ES 索引（已落库的数据才进索引）。"""
        if not self._orm_batch:
            return
        self._db.add_all(self._orm_batch)
        await self._db.commit()
        await bulk_index_reviews(
            [_to_es_doc(r, self._dataset.dataset_version) for r in self._row_batch],
            self._dataset.dataset_version,
        )
        self.imported += len(self._orm_batch)
        self._orm_batch = []
        self._row_batch = []

    async def finalize(self) -> None:
        """冲刷余量并回写数据集统计与质量报告。"""
        await self.flush()
        ds = self._dataset
        ds.total_rows = self.imported + self.rejected
        ds.valid_rows = self.imported
        ds.rejected_rows = self.rejected
        ds.quality_report = {
            "rejection_reasons": self.reasons,
            "reasons_detail": {},
        }
        ds.status = "completed"
        await self._db.commit()


async def run_import(ctx, dataset_version: str) -> dict:
    """导入任务主体。ctx 为 ARQ worker 上下文（未使用）。

    按批次「PG 提交 → ES 索引」推进：每批独立 commit 避免超大事务和
    ORM 对象全程驻留内存；bulk 按 dataset_version|review_id 幂等，
    失败重跑可自愈。
    """
    async with AsyncSessionLocal() as db:
        dataset = (
            await db.execute(
                select(Dataset).where(Dataset.dataset_version == dataset_version)
            )
        ).scalar_one_or_none()
        if dataset is None:
            return {"status": "failed", "message": "数据集不存在"}

        filename = dataset.storage_path.rsplit("/", 1)[-1]
        object_name = f"datasets/{dataset_version}/{filename}"
        importer = _StreamingImporter(db, dataset)

        async def process_line(line: str) -> None:
            stripped = line.strip()
            if not stripped:
                return
            normalized, errors = parse_jsonl_line(
                stripped, importer.mapping, importer.seen
            )
            if errors:
                importer.add_reasons(errors)
            else:
                importer.add_row(normalized)
                if importer.full:
                    await importer.flush()

        try:
            await ensure_reviews_index()

            if filename.endswith(".csv"):
                # CSV 字段可含引号内换行，需整体解析（与流式语义一致）
                content = await read_bytes(object_name)
                rows, reasons = parse_rows(content, dataset.field_mapping)
                for normalized in rows:
                    importer.add_row(normalized)
                    if importer.full:
                        await importer.flush()
                importer.reasons = reasons
                importer.rejected = sum(reasons.values())
            else:
                splitter = IncrementalLineSplitter(
                    gzip_encoded=filename.endswith(".gz")
                )
                async for chunk in iter_object_chunks(object_name):
                    for line in splitter.feed(chunk):
                        await process_line(line)
                for line in splitter.flush():
                    await process_line(line)

            await importer.finalize()
        except Exception as exc:  # noqa: BLE001  失败需落库标记
            await db.rollback()
            dataset.status = "failed"
            dataset.error_message = str(exc)[:1000]
            # 记录已完成批次进度，便于评估失败位置与重跑范围
            dataset.quality_report = {"imported_rows": importer.imported}
            await db.commit()
            return {
                "status": "failed",
                "message": str(exc),
                "imported_rows": importer.imported,
            }

    return {
        "status": "completed",
        "dataset_version": dataset_version,
        "valid_rows": importer.imported,
    }
