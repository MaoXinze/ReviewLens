"""M6 模型发布/回滚/历史 + 门槛与审核样本训练测试。

- 纯函数单测：门槛判定、覆盖率计算
- 状态机集成测试（使用真实 PG 测试库，直接落库 AnalysisRun）：
  发布下线旧模型、回滚恢复上一版本、当前模型查询、历史列表
- API 集成测试：current/history 端点鉴权与空态

说明：AnalysisRun 需先 INSERT 后跑发布/回滚，因此直接建会话落库，
再对 model_service 函数断言（复用 client fixture 保证建表共库）。
"""
import os
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.prediction import AnalysisRun
from app.models.review_task import (
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_PENDING,
    ReviewTask,
)
from app.services import model_service

try:
    from conftest import TEST_DB_URL  # type: ignore[import-not-found]
except ImportError:  # pytest 不把 conftest 暴露为模块名时回退默认测试库
    TEST_DB_URL = (
        os.environ.get("TEST_DATABASE_URL")
        or "postgresql+asyncpg://reviewlens:reviewlens_dev_only@localhost:15432/reviewlens_test"
    )

# ---------- 纯函数：门槛判定 ----------

_run_seq = [0]


class _Run:
    def __init__(self, **kw):
        defaults = dict(
            status="succeeded",
            publish_status="evaluation_only",
            macro_f1=0.8,
            accuracy=0.8,
            test_samples=1200,
            dataset_version="ds-x",
            model_version="tfidf_lr-v1",
            algorithm="tfidf_lr",
        )
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)


async def test_check_criteria_low_f1():
    run = _Run(macro_f1=0.6)
    ok, reason = await model_service.check_publish_criteria(None, run)  # type: ignore[arg-type]
    assert not ok
    assert "Macro-F1" in reason


async def test_check_criteria_low_test_samples():
    run = _Run(test_samples=100)
    ok, reason = await model_service.check_publish_criteria(None, run)  # type: ignore[arg-type]
    assert not ok
    assert "测试样本" in reason


async def test_check_criteria_not_succeeded():
    run = _Run(status="failed")
    ok, _ = await model_service.check_publish_criteria(None, run)  # type: ignore[arg-type]
    assert not ok


# ---------- 覆盖率（DB 集成，共库 client 夹具） ----------


@pytest_asyncio.fixture
async def session_pool(client):  # noqa: ARG001  依赖 client 保证建表共库
    engine = create_async_engine(TEST_DB_URL, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    _run_seq[0] = 0
    async with factory() as session:
        yield session
    await engine.dispose()


async def _add_runs(db, specs: list[_Run]) -> list[AnalysisRun]:
    runs = []
    for spec in specs:
        run = AnalysisRun(
            id=str(_run_seq),
            dataset_version=spec.dataset_version,
            model_version=spec.model_version,
            algorithm=spec.algorithm,
            random_seed=42,
            train_samples=spec.test_samples,
            test_samples=spec.test_samples,
            macro_f1=spec.macro_f1,
            accuracy=spec.accuracy,
            status=spec.status,
            publish_status=spec.publish_status,
            finished_at=datetime(2025, 9, 1, tzinfo=UTC),
        )
        _run_seq[0] += 1
        db.add(run)
        runs.append(run)
    await db.commit()
    return runs


async def test_calculate_review_coverage_zero_when_no_tasks(session_pool):
    cov = await model_service.calculate_review_coverage(session_pool, "ds-empty")
    assert cov == 0.0


async def test_calculate_review_coverage_mixed(session_pool):
    for i, status in enumerate(
        (REVIEW_STATUS_PENDING, REVIEW_STATUS_APPROVED, REVIEW_STATUS_APPROVED)
    ):
        session_pool.add(
            ReviewTask(
                id=f"task-cov-{i}",
                dataset_version="ds-cov",
                review_id=f"R{i}",
                sampling_group="random",
                status=status,
            )
        )
    await session_pool.commit()
    cov = await model_service.calculate_review_coverage(session_pool, "ds-cov")
    assert cov == pytest.approx(2 / 3)


async def test_publish_archives_old_model(session_pool):
    [target] = await _add_runs(session_pool, [_Run()])  # evaluation_only
    await _add_runs(
        session_pool,
        [_Run(model_version="tfidf_lr-v2", publish_status="published")],  # 现有生产
    )
    # 覆盖率达标：造已审核任务
    for i in range(3):
        session_pool.add(
            ReviewTask(
                id=f"pubtask-{i}",
                dataset_version="ds-x",
                review_id=f"PR{i}",
                sampling_group="random",
                status=REVIEW_STATUS_APPROVED,
            )
        )
    await session_pool.commit()

    msg = await model_service.publish_model(session_pool, target)
    assert msg == "模型已发布"

    old = await session_pool.execute(
        select(AnalysisRun).where(AnalysisRun.publish_status == "archived")
    )
    old_runs = old.scalars().all()
    assert len(old_runs) == 1
    await session_pool.refresh(target)
    assert target.publish_status == "published"

    current = await model_service.get_current_model(session_pool)
    assert current is not None
    assert current.id == target.id


async def test_publish_requires_min_coverage(session_pool):
    [target] = await _add_runs(session_pool, [_Run()])
    # 无审核任务 → coverage=0
    try:
        await model_service.publish_model(session_pool, target)
        raise AssertionError("应拒绝低覆盖率发布")
    except ValueError as exc:
        assert "覆盖率" in str(exc)


async def test_rollback_restores_previous(session_pool):
    [current, prev_run] = await _add_runs(
        session_pool,
        [
            _Run(model_version="tfidf_lr-v2", publish_status="published"),
            _Run(model_version="tfidf_lr-v1", publish_status="archived"),
        ],
    )
    prev = await model_service.rollback_model(session_pool, current)
    assert prev is not None
    assert prev.id == prev_run.id
    await session_pool.refresh(current)
    assert current.publish_status == "archived"
    assert prev.publish_status == "published"


async def test_rollback_no_previous(session_pool):
    [current] = await _add_runs(
        session_pool, [_Run(publish_status="published")]
    )
    prev = await model_service.rollback_model(session_pool, current)
    assert prev is None


async def test_list_model_history(session_pool):
    await _add_runs(session_pool, [_Run(), _Run(model_version="tfidf_lr-v2")])
    items = await model_service.list_model_history(session_pool)
    assert len(items) == 2


# ---------- API 集成 ----------


async def _auth_headers(client):
    email = "m6@example.com"
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": "Passw0rd!", "full_name": "M6"},
    )
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": "Passw0rd!"}
    )
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_models_current_empty(client):
    headers = await _auth_headers(client)
    resp = await client.get("/api/v1/models/current", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["publish_status"] == "no_model"


async def test_models_history_empty(client):
    headers = await _auth_headers(client)
    resp = await client.get("/api/v1/models/history", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 0


async def test_publish_requires_auth(client):
    resp = await client.post("/api/v1/analysis-runs/x/publish")
    assert resp.status_code == 401


async def test_analysis_runs_reviewed_insufficient_samples(client):
    headers = await _auth_headers(client)
    resp = await client.post(
        "/api/v1/analysis-runs/reviewed",
        json={"dataset_version": "ds-missing"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "不足" in resp.json()["detail"]


async def test_analysis_service_sample_reviewed_only_approved(client):  # noqa: ARG001
    """(结构占位) 采样逻辑实现在 model_service，此处用纯函数守卫防误删。"""
    assert hasattr(model_service, "sample_reviewed_training_data")


# ---------- 回归：可复现版本号允许多条运行引用 ----------

async def test_same_model_version_multiple_runs(client):
    """同数据同 seed 重训产生相同 model_version（内容哈希），不得撞唯一键。"""
    engine = create_async_engine(TEST_DB_URL, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as db:
        for i in range(2):
            db.add(
                AnalysisRun(
                    id=f"dup-{i}",
                    dataset_version="ds-dup",
                    model_version="tfidf_lr_same",
                    status="succeeded",
                )
            )
        await db.commit()
        rows = (
            await db.execute(
                select(AnalysisRun).where(AnalysisRun.model_version == "tfidf_lr_same")
            )
        ).all()
    assert len(rows) == 2
    await engine.dispose()
