"""M2 数据导入引擎测试。

覆盖：解析/校验纯函数、上传导入（含幂等）、鉴权、数据查询端点。
写入类接口通过 monkeypatch 屏蔽 MinIO 与 ARQ，测试保持无外部依赖。
"""
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.dataset import Dataset
from app.models.review import Review
from app.services import dataset_service
from tests.conftest import TEST_DB_URL


def _valid_line(review_id: str, **overrides) -> str:
    base = {
        "review_id": review_id,
        "asin": "p1",
        "title": "Nice",
        "text": "This product works great",
        "timestamp": 1700000000000,
        "rating": 5,
        "helpful_vote": 3,
        "verified_purchase": True,
    }
    base.update(overrides)
    return json.dumps(base)


def _jsonl(*lines) -> bytes:
    return ("\n".join(lines) + "\n").encode("utf-8")


# ---------- 解析 / 校验（纯函数，无 IO） ----------

async def test_parse_jsonl_valid_and_rejected():
    content = _jsonl(
        _valid_line("r1"),
        _valid_line("r2", text=""),  # empty_text -> reject
        _valid_line("r3", timestamp="not-a-date"),  # invalid_timestamp -> reject
        _valid_line("r1"),  # duplicate_id -> reject
        _valid_line("r4", text="x" * 6000),  # too_long -> reject
        _valid_line("r5"),  # valid
    )
    valid, reasons = dataset_service.parse_rows(content)
    assert len(valid) == 2
    assert ["r1", "r5"] == [row["review_id"] for row in valid]
    assert reasons["empty_text"] == 1
    assert reasons["invalid_timestamp"] == 1
    assert reasons["duplicate_id"] == 1
    assert reasons["too_long"] == 1
    assert valid[0]["language"] == "en"
    assert valid[0]["verified_purchase"] is True
    assert valid[0]["helpful_votes"] == 3


async def test_parse_jsonl_chinese_language():
    content = "".join(
        json.dumps(
            {
                "review_id": f"z{i}",
                "asin": "p2",
                "text": "这个产品非常好用，质量很棒，值得购买。",
                "timestamp": 1700000010000,
            }
        )
        + "\n"
        for i in range(3)
    ).encode("utf-8")
    valid, reasons = dataset_service.parse_rows(content)
    assert len(valid) == 3
    assert all(row["language"] in ("zh", "mixed") for row in valid)


async def test_parse_csv():
    csv_content = (
        b"review_id,asin,text,timestamp,rating\n"
        b"c1,p1,decent product,1700000000000,4\n"
    )
    valid, reasons = dataset_service.parse_rows(csv_content)
    assert len(valid) == 1
    assert valid[0]["review_id"] == "c1"
    assert valid[0]["rating"] == 4


async def test_parse_empty_file():
    valid, reasons = dataset_service.parse_rows(b"")
    assert valid == []
    assert reasons == {}

# ---------- 导入 API ----------

AUTH = {"email": "import@example.com", "password": "Passw0rd!"}


async def _register_and_token(client):
    await client.post("/api/auth/register", json=AUTH)
    login = await client.post("/api/auth/login", json=AUTH)
    return login.json()["data"]["access_token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


async def test_import_requires_auth(client):
    resp = await client.post(
        "/api/v1/datasets/imports",
        files={"file": ("a.jsonl", b"{}", "application/octet-stream")},
    )
    assert resp.status_code == 401


async def test_import_rejects_empty_file(client, monkeypatch):
    token = await _register_and_token(client)
    resp = await client.post(
        "/api/v1/datasets/imports",
        headers=_headers(token),
        files={"file": ("empty.jsonl", b"", "application/octet-stream")},
    )
    assert resp.status_code == 400


async def _patch_deps(monkeypatch):
    calls = {"enqueued": []}
    async def fake_enqueue(version):
        calls["enqueued"].append(version)
    async def fake_upload(object_name, data):
        calls.setdefault("uploads", []).append((object_name, len(data)))
    monkeypatch.setattr(dataset_service, "enqueue_import", fake_enqueue)
    monkeypatch.setattr(dataset_service, "upload_bytes", fake_upload)
    return calls


async def test_import_success_and_list(client, monkeypatch):
    token = await _register_and_token(client)
    calls = await _patch_deps(monkeypatch)
    content = _jsonl(_valid_line("a1"), _valid_line("a2"))
    resp = await client.post(
        "/api/v1/datasets/imports",
        headers=_headers(token),
        files={"file": ("reviews.jsonl", content, "application/octet-stream")},
    )
    assert resp.status_code == 202
    data = resp.json()["data"]
    assert data["reused"] is False
    assert data["dataset_version"].startswith("ds-")
    assert data["status"] == "queued"
    assert calls["enqueued"] == [data["dataset_version"]]

    lst = await client.get("/api/v1/datasets", headers=_headers(token))
    assert lst.status_code == 200
    assert lst.json()["data"]["total"] >= 1


async def test_import_reused(client, monkeypatch):
    token = await _register_and_token(client)
    calls = await _patch_deps(monkeypatch)
    content = _jsonl(_valid_line("a1"))
    first = await client.post(
        "/api/v1/datasets/imports", headers=_headers(token),
        files={"file": ("r.jsonl", content, "application/octet-stream")},
    )
    version = first.json()["data"]["dataset_version"]
    second = await client.post(
        "/api/v1/datasets/imports", headers=_headers(token),
        files={"file": ("r.jsonl", content, "application/octet-stream")},
    )
    sdata = second.json()["data"]
    assert second.status_code == 202
    assert sdata["reused"] is True
    assert sdata["dataset_version"] == version
    # 二次上传不应再次入队
    assert calls["enqueued"] == [version]


async def test_import_invalid_field_mapping(client):
    token = await _register_and_token(client)
    resp = await client.post(
        "/api/v1/datasets/imports", headers=_headers(token),
        files={"file": ("r.jsonl", b"{}", "application/octet-stream")},
        data={"field_mapping": "not-json"},
    )
    assert resp.status_code == 422

# ---------- 查询端点（直接种子数据） ----------

async def _seed_dataset():
    version = "ds-test0001"
    engine = create_async_engine(TEST_DB_URL, pool_pre_ping=True)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        ds = Dataset(
            id=str(uuid4()), dataset_version=version, source_filename="seed.jsonl",
            file_sha256="a" * 64, storage_path=f"datasets/{version}/seed.jsonl",
            field_mapping={}, status="completed",
            total_rows=3, valid_rows=3, rejected_rows=0,
            quality_report={"rejection_reasons": {}},
        )
        db.add(ds)
        db.add_all(
            [
                Review(id=str(uuid4()), dataset_version=version, review_id=f"r{i}",
                       product_id="p1", review_text=f"comment {i}", rating=4,
                       reviewed_at=datetime(2026, 9, 1, tzinfo=UTC), language="en")
                for i in range(3)
            ]
        )
        await db.commit()
    await engine.dispose()
    return version


async def test_datasets_detail_reviews_quality(client):
    token = await _register_and_token(client)
    version = await _seed_dataset()

    detail = await client.get(f"/api/v1/datasets/{version}", headers=_headers(token))
    assert detail.status_code == 200
    assert detail.json()["data"]["status"] == "completed"
    assert detail.json()["data"]["valid_rows"] == 3

    qr = await client.get(
        f"/api/v1/datasets/{version}/quality-report", headers=_headers(token)
    )
    assert qr.status_code == 200

    revs = await client.get(
        f"/api/v1/datasets/{version}/reviews", headers=_headers(token)
    )
    assert revs.status_code == 200
    assert revs.json()["data"]["total"] == 3
    assert len(revs.json()["data"]["items"]) == 3


async def test_dataset_not_found(client):
    token = await _register_and_token(client)
    resp = await client.get("/api/v1/datasets/ds-nope", headers=_headers(token))
    assert resp.status_code == 404
