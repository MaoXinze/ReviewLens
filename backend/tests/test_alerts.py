"""M9 告警与导出测试。

覆盖验收标准：
1. 阈值规则触发：差评率超阈值创建告警
2. 趋势规则触发：环比增长超阈值创建告警
3. 去重：同一规则在 dedup_days 内不重复触发
4. 告警状态流转：active → acknowledged → resolved（resolved 终态）
5. CSV 导出含评论原文 + 预测结果 + 审核标签
6. 导出文件存 MinIO，有下载链接

依赖 conftest 的真实 PG 测试库；ES 差评率与 MinIO 通过 monkeypatch 屏蔽。
"""
import os
from datetime import UTC, datetime, timedelta
from typing import NamedTuple
from uuid import uuid4

import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password
from app.models.alert import Alert, AlertRule
from app.models.base import Base
from app.models.dataset import Dataset
from app.models.prediction import ReviewPrediction
from app.models.review import Review
from app.models.review_task import ReviewTask
from app.models.user import User
from app.services import alert_service, export_service

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://reviewlens:reviewlens_dev_only@localhost:15432/reviewlens_test",
)

DS = "ds-alert"
ASPECT = "电池续航"

_CREATE_DEFAULT_PARTITION = """
CREATE TABLE IF NOT EXISTS reviews_default PARTITION OF reviews DEFAULT
"""


@pytest_asyncio.fixture
async def tables():
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


async def _seed_users_dataset():
    """写审计：operator/analyst + completed 数据集。"""
    engine = create_async_engine(TEST_DB_URL)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session() as s:
            operator = User(
                email="ops@alert.com",
                password_hash=hash_password("Passw0rd!"),
                full_name="Operator",
                role="operator",
            )
            analyst = User(
                email="analyst@alert.com",
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
                    source_filename="alert.jsonl",
                    file_sha256="a" * 64,
                    storage_path=f"datasets/{DS}/f.jsonl",
                    field_mapping={},
                    status="completed",
                    created_at=datetime.now(UTC) - timedelta(days=5),
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


async def _insert_rule(session, **overrides) -> AlertRule:
    """插入 active 规则；created_by 缺失时自动创建一个 analyst 用户。"""
    created_by = overrides.pop("created_by", None)
    if created_by is None:
        owner = User(
            email=f"owner-{uuid4().hex[:8]}@alert.com",
            password_hash=hash_password("Passw0rd!"),
            full_name="Owner",
            role="analyst",
        )
        session.add(owner)
        await session.flush()
        created_by = owner.id
    payload = dict(
        name="电池续航超阈值",
        rule_type="threshold",
        aspect=ASPECT,
        product_id=None,
        threshold_value=0.5,
        time_window_days=30,
        dedup_days=7,
        status="active",
        created_by=created_by,
    )
    payload.update(overrides)
    rule = AlertRule(id=str(uuid4()), **payload)
    session.add(rule)
    await session.flush()
    return rule


class _FakeLatest:
    dataset_version = DS


async def _fake_latest(db):
    """伪造 get_latest_dataset：返回最新数据集对象。"""
    return _FakeLatest()


class _RateResult:
    """伪造差评率返回值，可直接做 monkeypatch 的异步 rate。"""

    def __init__(self, r: float):
        self.r = r

    async def arate(self, _db, **kwargs):
        return self.r


# ---------- 验收标准 1：阈值触发 ----------


async def test_threshold_rule_triggers_alert(tables, monkeypatch):
    monkeypatch.setattr(
        alert_service, "get_latest_dataset", _fake_latest
    )
    monkeypatch.setattr(
        alert_service, "_aspect_negative_rate", _RateResult(0.85).arate
    )
    engine = create_async_engine(TEST_DB_URL)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session() as s:
            rule = await _insert_rule(s, threshold_value=0.5)  # 0.85 > 0.5
            await s.commit()
            result = await alert_service.run_alert_check(s)
            assert result["checked"] == 1
            assert result["created"] == 1
            alert = (
                await s.execute(
                    sa.select(Alert).where(Alert.rule_id == rule.id)
                )
            ).scalars().first()
            assert alert is not None
            assert alert.status == "active"
            assert alert.metric_value == 0.85
    finally:
        await engine.dispose()


async def test_threshold_rule_below_no_trigger(tables, monkeypatch):
    monkeypatch.setattr(alert_service, "get_latest_dataset", _fake_latest)
    monkeypatch.setattr(
        alert_service, "_aspect_negative_rate", _RateResult(0.30).arate
    )
    engine = create_async_engine(TEST_DB_URL)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session() as s:
            await _insert_rule(s, threshold_value=0.5)  # 0.30 <= 0.5
            await s.commit()
            result = await alert_service.run_alert_check(s)
            assert result["created"] == 0
    finally:
        await engine.dispose()


# ---------- 验收标准 2：趋势触发 ----------


async def test_trend_rule_triggers_on_growth(tables, monkeypatch):
    monkeypatch.setattr(alert_service, "get_latest_dataset", _fake_latest)

    async def fake_rate(_db, **kwargs):
        # prev 窗口（含 end_date）→ 0.30；当前窗口 → 0.60
        if kwargs.get("end_date") is not None:
            return 0.30
        return 0.60

    monkeypatch.setattr(alert_service, "_aspect_negative_rate", fake_rate)
    engine = create_async_engine(TEST_DB_URL)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session() as s:
            rule = await _insert_rule(
                s,
                rule_type="trend",
                threshold_value=0.5,  # growth = (0.6-0.3)/0.3 = 1.0 > 0.5
            )
            await s.commit()
            result = await alert_service.run_alert_check(s)
            assert result["created"] == 1
            alert = (
                await s.execute(
                    sa.select(Alert).where(Alert.rule_id == rule.id)
                )
            ).scalars().first()
            assert alert is not None
            assert alert.metric_value == 1.0  # growth
    finally:
        await engine.dispose()


async def test_trend_rule_no_trigger_below_threshold(tables, monkeypatch):
    monkeypatch.setattr(alert_service, "get_latest_dataset", _fake_latest)

    async def fake_rate(_db, **kwargs):
        if kwargs.get("end_date") is not None:
            return 0.40
        return 0.42  # growth = 0.05 < 0.5

    monkeypatch.setattr(alert_service, "_aspect_negative_rate", fake_rate)
    engine = create_async_engine(TEST_DB_URL)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session() as s:
            await _insert_rule(s, rule_type="trend", threshold_value=0.5)
            await s.commit()
            result = await alert_service.run_alert_check(s)
            assert result["created"] == 0
    finally:
        await engine.dispose()


# ---------- 验收标准 3：去重 ----------


async def test_dedup_no_repeat_within_window(tables, monkeypatch):
    monkeypatch.setattr(alert_service, "get_latest_dataset", _fake_latest)
    monkeypatch.setattr(
        alert_service, "_aspect_negative_rate", _RateResult(0.85).arate
    )
    engine = create_async_engine(TEST_DB_URL)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session() as s:
            await _insert_rule(s)
            await s.commit()
            first = await alert_service.run_alert_check(s)
            assert first["created"] == 1
            # 再次执行：同一规则 dedup_days 内已有告警 → 不重复触发
            second = await alert_service.run_alert_check(s)
            assert second["created"] == 0
            assert second["checked"] == 1
            total = (
                await s.execute(sa.select(sa.func.count()).select_from(Alert))
            ).scalar_one()
            assert int(total) == 1
    finally:
        await engine.dispose()


# ---------- 验收标准 4：状态流转 ----------


async def test_alert_status_flow_active_ack_resolve(tables):
    engine = create_async_engine(TEST_DB_URL)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session() as s:
            operator = User(
                email="ops@flow.com",
                password_hash=hash_password("Passw0rd!"),
                full_name="Operator",
                role="operator",
            )
            s.add(operator)
            await s.flush()
            rule = await _insert_rule(s, created_by=operator.id)
            alert = Alert(
                id=str(uuid4()),
                rule_id=rule.id,
                aspect=ASPECT,
                product_id=None,
                metric_value=0.85,
                trigger_value=0.5,
                status="active",
                triggered_at=datetime.now(UTC),
            )
            s.add(alert)
            await s.commit()

            # active → acknowledged
            alert = await alert_service.update_alert_status(
                s, alert, status="acknowledged", operator=operator
            )
            assert alert.status == "acknowledged"
            # acknowledged → resolved
            alert = await alert_service.update_alert_status(
                s, alert, status="resolved", operator=operator
            )
            assert alert.status == "resolved"
            assert alert.resolved_by == operator.id
            assert alert.resolved_at is not None
            # resolved 终态不可流转 → 400
            try:
                await alert_service.update_alert_status(
                    s, alert, status="acknowledged", operator=operator
                )
                raise AssertionError("resolved 不应可流转")
            except ValueError:
                pass
    finally:
        await engine.dispose()


async def test_alert_skip_ack_to_resolve_ok(tables):
    """active 直接 resolved 也应允许（active→resolved 在白名单内）。"""
    engine = create_async_engine(TEST_DB_URL)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session() as s:
            operator = User(
                email="ops@flow2.com",
                password_hash=hash_password("Passw0rd!"),
                full_name="Operator",
                role="operator",
            )
            s.add(operator)
            await s.flush()
            rule = await _insert_rule(s, created_by=operator.id)
            alert = Alert(
                id=str(uuid4()), rule_id=rule.id, aspect=ASPECT,
                product_id=None, metric_value=0.9, trigger_value=0.5,
                status="active", triggered_at=datetime.now(UTC),
            )
            s.add(alert)
            await s.commit()
            alert = await alert_service.update_alert_status(
                s, alert, status="resolved", operator=operator
            )
            assert alert.status == "resolved"
    finally:
        await engine.dispose()


# ---------- 验收标准 5：CSV 导出内容 ----------


class _Row(NamedTuple):
    review_id: str
    product_id: str
    rating: int
    reviewed_at: datetime
    review_text: str
    pred_sentiment: str
    confidence: float
    reviewer_sentiment: str


async def test_build_csv_contains_original_prediction_review_label():
    rows = [
        _Row("R1", "B001", 2, datetime(2026, 8, 1, 10, 0, 0, tzinfo=UTC),
             "电池续航很差", "negative", 0.92, "negative"),
        _Row("R2", "B001", 4, datetime(2026, 8, 2, 11, 0, 0, tzinfo=UTC),
             "质量不错", "positive", 0.88, ""),
    ]
    csv_text = export_service.build_csv(rows)
    assert csv_text.splitlines()[0] == ",".join(export_service.CSV_HEADERS)
    assert "电池续航很差" in csv_text
    assert "negative" in csv_text
    assert "0.92" in csv_text
    assert "R1" in csv_text
    assert "R2" in csv_text


# ---------- 验收标准 6：导出存储 MinIO + 下载 ----------


async def _seed_export_data():
    """数据集 + 评论 + 预测 + 已审核任务 + analyst 用户，供导出测试。"""
    engine = create_async_engine(TEST_DB_URL)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session() as s:
            analyst = User(
                email="analyst@exp.com",
                password_hash=hash_password("Passw0rd!"),
                full_name="Analyst",
                role="analyst",
            )
            s.add(analyst)
            await s.flush()
            now = datetime.now(UTC)
            s.add(
                Dataset(
                    id=str(uuid4()), dataset_version=DS,
                    source_filename="a.jsonl", file_sha256="b" * 64,
                    storage_path="d", field_mapping={}, status="completed",
                    created_at=now - timedelta(days=5),
                )
            )
            s.add(
                Review(
                    id=str(uuid4()), dataset_version=DS, review_id="E1",
                    product_id="B001", review_text="电池续航差，发热严重",
                    rating=2, reviewed_at=now - timedelta(days=3),
                    created_at=now,
                )
            )
            s.add(
                Review(
                    id=str(uuid4()), dataset_version=DS, review_id="E2",
                    product_id="B001", review_text="整体满意，音质不错",
                    rating=4, reviewed_at=now - timedelta(days=2),
                    created_at=now,
                )
            )
            s.add(
                ReviewPrediction(
                    id=str(uuid4()), dataset_version=DS, review_id="E1",
                    model_version="m1", overall_sentiment="negative",
                    confidence=0.9, aspects=[], created_at=now,
                )
            )
            s.add(
                ReviewPrediction(
                    id=str(uuid4()), dataset_version=DS, review_id="E2",
                    model_version="m1", overall_sentiment="positive",
                    confidence=0.8, aspects=[], created_at=now,
                )
            )
            s.add(
                ReviewTask(
                    id=str(uuid4()), dataset_version=DS, review_id="E1",
                    sampling_group="random", status="approved",
                    system_sentiment="negative", system_confidence=0.9,
                    reviewer_sentiment="negative", model_version="m1",
                    created_at=now,
                )
            )
            await s.commit()
            return {
                "analyst_id": analyst.id,
                "analyst_token": create_access_token(analyst.id, analyst.role),
            }
    finally:
        await engine.dispose()


def _run_req(**overrides) -> object:
    payload = dict(dataset_version=DS, product_id=None, sentiment=None,
                   rating_min=None, rating_max=None)
    payload.update(overrides)
    return type("R", (), payload)()


async def test_export_records_and_uploads(monkeypatch):
    seed = await _seed_export_data()
    uploaded = {}

    async def fake_upload(object_name, data):
        uploaded["name"] = object_name
        uploaded["data"] = data

    async def fake_current(db):
        return type("M", (), {"model_version": "m1"})()

    monkeypatch.setattr(export_service, "upload_bytes", fake_upload)
    monkeypatch.setattr(
        export_service.model_service, "get_current_model", fake_current
    )
    engine = create_async_engine(TEST_DB_URL)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session() as s:
            record = await export_service.export_reviews(
                s, req=_run_req(), user_id=seed["analyst_id"]
            )
            assert record.row_count == 2
            assert record.file_path.startswith(
                f"exports/{seed['analyst_id']}/"
            )
            assert uploaded["name"] == record.file_path
            assert uploaded["data"].decode("utf-8-sig").startswith(
                "review_id,"
            )
    finally:
        await engine.dispose()


async def test_export_download_endpoint(client, monkeypatch):
    seed = await _seed_export_data()
    uploaded = {}

    async def fake_upload(object_name, data):
        uploaded["name"] = object_name

    async def fake_read(object_name):
        return "review_id,review_text\nE1,电池续航差\n".encode()

    async def fake_current(db):
        return type("M", (), {"model_version": "m1"})()

    monkeypatch.setattr(export_service, "upload_bytes", fake_upload)
    monkeypatch.setattr(export_service, "read_bytes", fake_read)
    monkeypatch.setattr(
        export_service.model_service, "get_current_model", fake_current
    )

    # analyst 导出
    resp = await client.post(
        "/api/v1/exports",
        headers=_headers(seed["analyst_token"]),
        json={"dataset_version": DS},
    )
    assert resp.status_code == 201
    export_id = resp.json()["data"]["id"]

    # 列表
    lst = await client.get(
        "/api/v1/exports", headers=_headers(seed["analyst_token"])
    )
    assert lst.status_code == 200
    assert lst.json()["data"]["total"] == 1

    # 下载返回 CSV
    dl = await client.get(
        f"/api/v1/exports/{export_id}/download",
        headers=_headers(seed["analyst_token"]),
    )
    assert dl.status_code == 200
    assert "text/csv" in dl.headers["content-type"]
    assert "电池续航差" in dl.text


# ---------- 规则 API 权限 ----------


async def test_create_rule_role_required(client):
    seed = await _seed_users_dataset()
    resp = await client.post(
        "/api/v1/alert-rules",
        headers=_headers(seed["ops"]),  # operator 无权限建规则
        json={
            "name": "阈值规则", "rule_type": "threshold", "aspect": ASPECT,
            "threshold_value": 0.5,
        },
    )
    assert resp.status_code == 403


async def test_create_rule_and_pause(client):
    seed = await _seed_users_dataset()
    resp = await client.post(
        "/api/v1/alert-rules",
        headers=_headers(seed["analyst"]),
        json={
            "name": "电池续航超阈值", "rule_type": "threshold",
            "aspect": ASPECT, "threshold_value": 0.5, "time_window_days": 30,
            "dedup_days": 7,
        },
    )
    assert resp.status_code == 201
    rule_id = resp.json()["data"]["id"]
    assert resp.json()["data"]["status"] == "active"

    # 暂停
    paused = await client.patch(
        f"/api/v1/alert-rules/{rule_id}",
        headers=_headers(seed["analyst"]),
        json={"status": "paused"},
    )
    assert paused.status_code == 200
    assert paused.json()["data"]["status"] == "paused"

    # 列表
    lst = await client.get("/api/v1/alert-rules", headers=_headers(seed["analyst"]))
    assert lst.status_code == 200
    assert lst.json()["data"]["total"] == 1
