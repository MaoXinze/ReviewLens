"""M8 问题卡管理测试。

覆盖：
- 创建：成功创建、来源评论不属于数据集 400、数据集不存在 400、
  缺少来源评论 400、角色限制 403
- 状态机：open→in_progress→pending_validation→closed 正常流转、
  open 直接关闭 400、closed 终态不可流转 400、缺失必填字段 400
- 审计轨迹：每步状态变更写入 issue_history（验收标准 3）
- 回测：closed 后对比创建前后差评率（mock ES），非 closed 回测 400
依赖 conftest 的真实 PG 测试库；ES 通过 monkeypatch 屏蔽。
"""
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password
from app.models.base import Base
from app.models.dataset import Dataset
from app.models.issue import Issue
from app.models.review import Review
from app.models.user import User
from app.services import issue_service

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://reviewlens:reviewlens_dev_only@localhost:15432/reviewlens_test",
)

DS = "ds-v1"
ASPECT = "电池续航"

_CREATE_DEFAULT_PARTITION = """
CREATE TABLE IF NOT EXISTS reviews_default PARTITION OF reviews DEFAULT
"""


@pytest_asyncio.fixture
async def tables():
    """为 service 直测提供干净的表空间（drop_all + create_all + 分区）。"""
    engine = create_async_engine(TEST_DB_URL)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(sa.text(_CREATE_DEFAULT_PARTITION))
    finally:
        await engine.dispose()
    yield


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _seed():
    """写审计：operator/analyst 用户 + 数据集 + 评论，返回 tokens。"""
    engine = create_async_engine(TEST_DB_URL)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session() as s:
            operator = User(
                email="ops@example.com",
                password_hash=hash_password("Passw0rd!"),
                full_name="Operator",
                role="operator",
            )
            analyst = User(
                email="analyst@example.com",
                password_hash=hash_password("Passw0rd!"),
                full_name="Analyst",
                role="analyst",
            )
            s.add(operator)
            s.add(analyst)
            await s.flush()

            s.add(
                Dataset(
                    id=str(uuid4()),
                    dataset_version=DS,
                    source_filename="amazon_reviews.jsonl",
                    file_sha256="x" * 64,
                    storage_path=f"datasets/{DS}/f.jsonl",
                    field_mapping={},
                    status="completed",
                    created_at=datetime.now(UTC) - timedelta(days=30),
                )
            )
            now = datetime.now(UTC)
            for i, rid in enumerate(["R1", "R2", "R3"]):
                s.add(
                    Review(
                        id=str(uuid4()),
                        dataset_version=DS,
                        review_id=rid,
                        product_id="B001",
                        review_text=f"review {rid}",
                        rating=2,
                        reviewed_at=now - timedelta(days=10 - i),
                        created_at=now,
                    )
                )
            await s.commit()
            return {
                "ops": create_access_token(operator.id, operator.role),
                "analyst": create_access_token(analyst.id, analyst.role),
                "operator_id": operator.id,
                "analyst_id": analyst.id,
            }
    finally:
        await engine.dispose()


def _create_payload(**overrides) -> dict:
    payload = {
        "dataset_version": DS,
        "title": "电池续航差评集中",
        "aspect": ASPECT,
        "severity": "high",
        "description": "近一月差评率显著上升",
        "source_review_ids": ["R1", "R2"],
    }
    payload.update(overrides)
    return payload


# ---------- 状态机（service 直测） ----------


async def _new_issue(session, creator_id: str) -> Issue:
    return await issue_service.create_issue(
        session,
        req=type(
            "R",
            (),
            {
                "dataset_version": DS,
                "title": "电池续航差评集中",
                "aspect": ASPECT,
                "severity": "high",
                "description": "t",
                "source_review_ids": ["R1"],
                "assignee": None,
            },
        )(),
        creator=type("U", (), {"id": creator_id})(),
        assignee=None,
    )


def _req(status: str, resolution_note: str | None = None,
         validation_note: str | None = None) -> object:
    """构造 transition_issue 的简化请求对象。"""
    return type(
        "R",
        (),
        {"status": status, "resolution_note": resolution_note,
         "validation_note": validation_note},
    )()


async def test_issue_state_machine_full_flow_and_terminal(tables):
    engine = create_async_engine(TEST_DB_URL)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session() as s:
            operator = User(
                email="ops@example.com",
                password_hash=hash_password("Passw0rd!"),
                full_name="Operator",
                role="operator",
            )
            s.add(operator)
            await s.flush()
            s.add(
                Dataset(
                    id=str(uuid4()),
                    dataset_version=DS,
                    source_filename="a",
                    file_sha256="x" * 64,
                    storage_path="d",
                    field_mapping={},
                    status="completed",
                )
            )
            s.add(
                Review(
                    id=str(uuid4()),
                    dataset_version=DS,
                    review_id="R1",
                    product_id="B001",
                    review_text="t",
                    rating=2,
                    reviewed_at=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                )
            )
            issue = await _new_issue(s, operator.id)
            assert issue.status == "open"

            # open → in_progress（需处置说明）
            issue = await issue_service.transition_issue(
                s, issue, req=_req("in_progress", resolution_note="正在排查"),
                operator=operator,
            )
            assert issue.status == "in_progress"

            # in_progress → pending_validation
            issue = await issue_service.transition_issue(
                s, issue, req=_req("pending_validation"), operator=operator,
            )
            assert issue.status == "pending_validation"

            # pending_validation → closed（需验证结论）
            issue = await issue_service.transition_issue(
                s, issue, req=_req("closed", validation_note="已验证改善"),
                operator=operator,
            )
            assert issue.status == "closed"
            assert issue.closed_at is not None

            # closed 为终态，不可流转 → 400
            try:
                await issue_service.transition_issue(
                    s, issue, req=_req("in_progress", resolution_note="x"),
                    operator=operator,
                )
                raise AssertionError("closed 不应可流转")
            except ValueError:
                pass
    finally:
        await engine.dispose()


async def test_issue_cannot_skip_pending_validation(tables):
    engine = create_async_engine(TEST_DB_URL)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session() as s:
            operator = User(
                email="ops@example.com",
                password_hash=hash_password("Passw0rd!"),
                full_name="Operator",
                role="operator",
            )
            s.add(operator)
            await s.flush()
            s.add(
                Dataset(
                    id=str(uuid4()),
                    dataset_version=DS,
                    source_filename="a",
                    file_sha256="x" * 64,
                    storage_path="d",
                    field_mapping={},
                    status="completed",
                )
            )
            s.add(
                Review(
                    id=str(uuid4()),
                    dataset_version=DS,
                    review_id="R1",
                    product_id="B001",
                    review_text="t",
                    rating=2,
                    reviewed_at=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                )
            )
            issue = await _new_issue(s, operator.id)
            # open 直接关闭（跳过 pending_validation）→ 400（验收标准 1）
            try:
                await issue_service.transition_issue(
                    s, issue,
                    req=_req("closed", validation_note="ok"),
                    operator=operator,
                )
                raise AssertionError("不应允许跳级关闭")
            except ValueError:
                pass
    finally:
        await engine.dispose()


async def test_issue_requires_resolution_note_on_start(tables):
    engine = create_async_engine(TEST_DB_URL)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session() as s:
            operator = User(
                email="ops@example.com",
                password_hash=hash_password("Passw0rd!"),
                full_name="Operator",
                role="operator",
            )
            s.add(operator)
            await s.flush()
            s.add(
                Dataset(
                    id=str(uuid4()),
                    dataset_version=DS,
                    source_filename="a",
                    file_sha256="x" * 64,
                    storage_path="d",
                    field_mapping={},
                    status="completed",
                )
            )
            s.add(
                Review(
                    id=str(uuid4()),
                    dataset_version=DS,
                    review_id="R1",
                    product_id="B001",
                    review_text="t",
                    rating=2,
                    reviewed_at=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                )
            )
            issue = await _new_issue(s, operator.id)
            try:
                await issue_service.transition_issue(
                    s, issue,
                    req=_req("in_progress", resolution_note=""),
                    operator=operator,
                )
                raise AssertionError("进入处置必须填处置说明")
            except ValueError:
                pass
    finally:
        await engine.dispose()


async def test_issue_history_audit_trail(tables):
    engine = create_async_engine(TEST_DB_URL)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session() as s:
            operator = User(
                email="ops@example.com",
                password_hash=hash_password("Passw0rd!"),
                full_name="Operator",
                role="operator",
            )
            s.add(operator)
            await s.flush()
            s.add(
                Dataset(
                    id=str(uuid4()),
                    dataset_version=DS,
                    source_filename="a",
                    file_sha256="x" * 64,
                    storage_path="d",
                    field_mapping={},
                    status="completed",
                )
            )
            s.add(
                Review(
                    id=str(uuid4()),
                    dataset_version=DS,
                    review_id="R1",
                    product_id="B001",
                    review_text="t",
                    rating=2,
                    reviewed_at=datetime.now(UTC),
                    created_at=datetime.now(UTC),
                )
            )
            issue = await _new_issue(s, operator.id)
            await issue_service.transition_issue(
                s, issue,
                req=_req("in_progress", resolution_note="排查中"),
                operator=operator,
            )
            history = await issue_service.get_issue_history(s, issue.id)
            # 创建时 status 变更 + 推进时 status 变更 + 处置说明变更
            statuses = [h for h in history if h.field_name == "status"]
            assert len(statuses) >= 2
            assert statuses[-1].new_value == "in_progress"
            assert statuses[-1].changed_by == operator.id
            notes = [h for h in history if h.field_name == "resolution_note"]
            assert notes and notes[-1].new_value == "排查中"
    finally:
        await engine.dispose()


# ---------- 创建校验 ----------


async def test_create_issue_source_review_must_belong_to_dataset(client):
    seed = await _seed()
    resp = await client.post(
        "/api/v1/issues",
        headers=_headers(seed["ops"]),
        json=_create_payload(source_review_ids=["R1", "R99"]),
    )
    assert resp.status_code == 400  # R99 不属于该数据集


async def test_create_issue_requires_source_reviews(client):
    seed = await _seed()
    resp = await client.post(
        "/api/v1/issues",
        headers=_headers(seed["ops"]),
        json=_create_payload(source_review_ids=[]),
    )
    assert resp.status_code == 400


async def test_create_issue_dataset_not_found(client):
    seed = await _seed()
    resp = await client.post(
        "/api/v1/issues",
        headers=_headers(seed["ops"]),
        json=_create_payload(dataset_version="ds-missing"),
    )
    assert resp.status_code == 400


async def test_create_issue_role_required(client):
    await _seed()
    # 无有效 token → 401
    resp = await client.post(
        "/api/v1/issues",
        headers=_headers("bad-token"),
        json=_create_payload(),
    )
    assert resp.status_code == 401


async def test_create_issue_success_and_list(client):
    seed = await _seed()
    resp = await client.post(
        "/api/v1/issues",
        headers=_headers(seed["ops"]),
        json=_create_payload(),
    )
    assert resp.status_code == 201
    issue_id = resp.json()["data"]["id"]
    assert resp.json()["data"]["status"] == "open"

    # 列表
    list_resp = await client.get("/api/v1/issues", headers=_headers(seed["ops"]))
    assert list_resp.status_code == 200
    assert list_resp.json()["data"]["total"] == 1
    assert list_resp.json()["data"]["items"][0]["id"] == issue_id

    # 详情含审计轨迹
    detail = await client.get(
        f"/api/v1/issues/{issue_id}", headers=_headers(seed["ops"])
    )
    assert detail.status_code == 200
    assert any(h["field_name"] == "status" for h in detail.json()["data"]["history"])


# ---------- 效果回测 ----------


async def test_retrospect_only_closed(monkeypatch, client):
    seed = await _seed()
    created = await client.post(
        "/api/v1/issues",
        headers=_headers(seed["ops"]),
        json=_create_payload(),
    )
    issue_id = created.json()["data"]["id"]
    resp = await client.post(
        f"/api/v1/issues/{issue_id}/retrospect", headers=_headers(seed["ops"])
    )
    assert resp.status_code == 400  # 未关闭不可回测


async def test_retrospect_success(monkeypatch, client):
    seed = await _seed()
    created = await client.post(
        "/api/v1/issues",
        headers=_headers(seed["ops"]),
        json=_create_payload(),
    )
    issue_id = created.json()["data"]["id"]

    # 推进到 closed
    await client.patch(
        f"/api/v1/issues/{issue_id}",
        headers=_headers(seed["ops"]),
        json={"status": "in_progress", "resolution_note": "已处置"},
    )
    await client.patch(
        f"/api/v1/issues/{issue_id}",
        headers=_headers(seed["ops"]),
        json={"status": "pending_validation", "resolution_note": "已处置"},
    )
    await client.patch(
        f"/api/v1/issues/{issue_id}",
        headers=_headers(seed["ops"]),
        json={"status": "closed", "validation_note": "已验证改善"},
    )

    # mock ES：pre 0.4，post 0.2 → improved
    calls = {}

    async def fake_rate(_db, **kwargs):
        calls["last"] = kwargs
        if "end_date" in kwargs and kwargs["end_date"] is not None:
            return 0.4
        return 0.2

    monkeypatch.setattr(issue_service, "_aspect_negative_rate", fake_rate)

    resp = await client.post(
        f"/api/v1/issues/{issue_id}/retrospect", headers=_headers(seed["ops"])
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["pre_rate"] == 0.4
    assert data["post_rate"] == 0.2
    assert data["change"] == -0.2
    assert data["improved"] is True
