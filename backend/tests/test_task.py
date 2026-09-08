"""M2 导入任务（ARQ worker）及 ES/MinIO 工具测试。

通过 monkeypatch 屏蔽 Redis / MinIO / ES 真实连接，仅保留 PG 落库与逻辑分支覆盖。
"""
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.dataset import Dataset
from app.tasks import import_task
from tests.conftest import TEST_DB_URL

_EN = datetime(2026, 9, 1, tzinfo=UTC)


async def _make_session():
    engine = create_async_engine(TEST_DB_URL, pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _content() -> bytes:
    lines = [
        '{"review_id":"w1","asin":"p1","text":"great",'
        '"timestamp":1700000000000,"rating":5}',
        '{"review_id":"w2","asin":"p1","text":"meh",'
        '"timestamp":1700000000001,"rating":3}',
    ]
    return ("\n".join(lines) + "\n").encode()


# ---------- 纯辅助函数 ----------

def test_to_es_doc():
    row = {"review_id": "w1", "reviewed_at": _EN, "text": "x"}
    doc = import_task._to_es_doc(row, "ds-1")
    assert doc["dataset_version"] == "ds-1"
    assert doc["reviewed_at"] == "2026-09-01T00:00:00+00:00"


def test_to_orm():
    row = {
        "review_id": "w1",
        "product_id": "p1",
        "review_text": "ok",
        "rating": 4,
        "reviewed_at": _EN,
        "language": "en",
    }
    orm = import_task._to_orm(row, "ds-1")
    assert orm.dataset_version == "ds-1"
    assert orm.review_id == "w1"
    assert orm.review_text == "ok"
    assert orm.reviewed_at == _EN


# ---------- run_import（写 PG，屏蔽 MinIO/ES/Redis） ----------

async def _seed_record(sess, version: str, filename: str = "a.jsonl"):
    async with sess() as db:
        db.add(
            Dataset(
                id="x",
                dataset_version=version,
                source_filename=filename,
                file_sha256="a" * 64,
                storage_path=f"datasets/{version}/{filename}",
                field_mapping={},
                status="importing",
            )
        )
        await db.commit()


async def test_run_import_completed(client, monkeypatch):
    version = "ds-task1"
    engine, sess = await _make_session()
    await _seed_record(sess, version)

    calls = {"bulk": []}

    async def fake_chunks(_name):
        yield _content()

    async def fake_ensure():
        return None

    async def fake_bulk(docs, _dv):
        calls["bulk"].append(len(docs))

    monkeypatch.setattr(import_task, "AsyncSessionLocal", sess)
    monkeypatch.setattr(import_task, "iter_object_chunks", fake_chunks)
    monkeypatch.setattr(import_task, "ensure_reviews_index", fake_ensure)
    monkeypatch.setattr(import_task, "bulk_index_reviews", fake_bulk)

    result = await import_task.run_import(None, version)
    assert result["status"] == "completed"
    assert result["valid_rows"] == 2
    assert calls["bulk"] == [2]

    async with sess() as db:
        ds = await db.get(Dataset, "x")
        assert ds.status == "completed"
        assert ds.valid_rows == 2
        assert ds.rejected_rows == 0
        assert ds.quality_report["rejection_reasons"] == {}
    await engine.dispose()


async def test_run_import_streaming_multichunk(client, monkeypatch):
    """跨块断行 + 拒绝行 + 分批落库：流式路径端到端。"""
    version = "ds-task3"
    engine, sess = await _make_session()
    await _seed_record(sess, version)

    lines = [
        '{"review_id":"w1","asin":"p1","text":"great",'
        '"timestamp":1700000000000,"rating":5}',
        '{"review_id":"w2","asin":"p1","text":"fine",'
        '"timestamp":1700000000001,"rating":4}',
        '{"review_id":"w1","asin":"p1","text":"dup",'
        '"timestamp":1700000000002,"rating":1}',  # 重复 id → 拒绝
        '{"asin":"p2","text":"no id",'
        '"timestamp":1700000000003,"rating":2}',  # 缺 id → 拒绝
    ]
    whole = ("\n".join(lines) + "\n").encode()
    # 在第一行中间切断，验证增量行重组
    cut = whole.index(b"1700000000001")

    async def fake_chunks(_name):
        yield whole[:cut]
        yield whole[cut:]

    async def fake_bulk(docs, _dv):
        return None

    monkeypatch.setattr(import_task, "AsyncSessionLocal", sess)
    monkeypatch.setattr(import_task, "iter_object_chunks", fake_chunks)

    async def fake_ensure():
        return None

    monkeypatch.setattr(import_task, "ensure_reviews_index", fake_ensure)
    monkeypatch.setattr(import_task, "bulk_index_reviews", fake_bulk)

    result = await import_task.run_import(None, version)
    assert result["status"] == "completed"
    assert result["valid_rows"] == 2

    async with sess() as db:
        ds = await db.get(Dataset, "x")
        assert ds.valid_rows == 2
        assert ds.rejected_rows == 2
        assert ds.quality_report["rejection_reasons"] == {
            "duplicate_id": 1,
            "missing_review_id": 1,
        }
    await engine.dispose()


async def test_run_import_gzip(client, monkeypatch):
    """.gz 压缩 JSONL 流式导入。"""
    import gzip as _gzip

    version = "ds-task4"
    engine, sess = await _make_session()
    await _seed_record(sess, version, filename="a.jsonl.gz")

    async def fake_chunks(_name):
        yield _gzip.compress(_content())

    async def fake_bulk(docs, _dv):
        return None

    async def fake_ensure():
        return None

    monkeypatch.setattr(import_task, "AsyncSessionLocal", sess)
    monkeypatch.setattr(import_task, "iter_object_chunks", fake_chunks)
    monkeypatch.setattr(import_task, "ensure_reviews_index", fake_ensure)
    monkeypatch.setattr(import_task, "bulk_index_reviews", fake_bulk)

    result = await import_task.run_import(None, version)
    assert result["status"] == "completed"
    assert result["valid_rows"] == 2
    await engine.dispose()


async def test_run_import_dataset_not_found(client, monkeypatch):
    engine, sess = await _make_session()
    monkeypatch.setattr(import_task, "AsyncSessionLocal", sess)
    result = await import_task.run_import(None, "ds-none")
    assert result["status"] == "failed"
    await engine.dispose()


async def test_run_import_failed_marks_record(client, monkeypatch):
    version = "ds-task2"
    engine, sess = await _make_session()
    await _seed_record(sess, version)

    async def boom(_name):
        raise RuntimeError("minio broken")
        yield  # pragma: no cover — 使其成为异步生成器

    monkeypatch.setattr(import_task, "AsyncSessionLocal", sess)
    monkeypatch.setattr(import_task, "iter_object_chunks", boom)

    result = await import_task.run_import(None, version)
    assert result["status"] == "failed"
    assert "minio broken" in result["message"]

    async with sess() as db:
        ds = await db.get(Dataset, "x")
        assert ds.status == "failed"
        assert "minio broken" in ds.error_message
    await engine.dispose()


# ---------- Elasticsearch 工具 ----------

class _FakeIndices:
    def __init__(self, exists_result: bool):
        self.exists_result = exists_result
        self.create_called = False

    async def exists(self, **kwargs):
        return self.exists_result

    async def create(self, **kwargs):
        self.create_called = True


class _FakeES:
    def __init__(self, exists_result: bool = True):
        self.indices = _FakeIndices(exists_result)
        self.bulk_ops = None
        self.closed = False

    async def bulk(self, operations=None):
        self.bulk_ops = operations
        return {}

    async def close(self):
        self.closed = True


async def test_ensure_reviews_index_exists(monkeypatch):
    from app.core import es

    ex = _FakeES(exists_result=True)
    monkeypatch.setattr(es, "_client", ex)
    monkeypatch.setattr(es, "get_es", lambda: ex)
    await es.ensure_reviews_index()
    assert es._client.indices.create_called is False


async def test_ensure_reviews_index_create(monkeypatch):
    from app.core import es

    ex = _FakeES(exists_result=False)
    monkeypatch.setattr(es, "_client", ex)
    monkeypatch.setattr(es, "get_es", lambda: ex)
    await es.ensure_reviews_index()
    assert es._client.indices.create_called is True


async def test_bulk_index_reviews_empty(monkeypatch):
    from app.core import es

    ex = _FakeES()
    monkeypatch.setattr(es, "_client", ex)
    monkeypatch.setattr(es, "get_es", lambda: ex)
    await es.bulk_index_reviews([], "ds-1")
    assert ex.bulk_ops is None


async def test_bulk_index_reviews_builds_ops(monkeypatch):
    from app.core import es

    ex = _FakeES()
    monkeypatch.setattr(es, "_client", ex)
    monkeypatch.setattr(es, "get_es", lambda: ex)
    await es.bulk_index_reviews([{"review_id": "w1", "rating": 5}], "ds-1")
    assert ex.bulk_ops[0]["index"]["_id"] == "ds-1|w1"
    assert ex.bulk_ops[1]["rating"] == 5


# ---------- MinIO 工具 ----------

class _FakeResp:
    def read(self):
        return b"raw-data"

    def close(self):
        return None

    def release_conn(self):
        return None


class _FakeMinio:
    def __init__(self):
        self.put = None
        self.bucket_made = False

    def bucket_exists(self, name):
        return True

    def make_bucket(self, name):
        self.bucket_made = True

    def put_object(self, bucket, name, data, length):
        self.put = (name, length, data.getvalue())

    def get_object(self, bucket, name):
        return _FakeResp()


async def test_ensure_bucket_and_upload(monkeypatch):
    from app.core import minio as m

    fake = _FakeMinio()
    monkeypatch.setattr(m, "get_minio", lambda: fake)
    monkeypatch.setattr(m.settings, "minio_bucket", "reviews")
    await m.ensure_bucket()
    assert fake.bucket_made is False
    await m.upload_bytes("datasets/ds-1/a.jsonl", b"hello")
    assert fake.put is not None
    assert fake.put[1] == 5


async def test_read_bytes(monkeypatch):
    from app.core import minio as m

    fake = _FakeMinio()
    monkeypatch.setattr(m, "get_minio", lambda: fake)
    monkeypatch.setattr(m.settings, "minio_bucket", "reviews")
    assert await m.read_bytes("datasets/ds-1/a.jsonl") == b"raw-data"


# ---------- ARQ worker 入口 ----------

def test_worker_main(monkeypatch):
    from app import worker

    calls = []

    class FakeWorker:
        def __init__(self, functions, cron_jobs=None, redis_settings=None, url=None):
            self.url = url
            self.functions = functions
            self.cron_jobs = cron_jobs
            self.redis_settings = redis_settings

        def run(self):
            calls.append("run")

    monkeypatch.setattr(worker, "Worker", FakeWorker)
    worker.main()
    assert calls == ["run"]
