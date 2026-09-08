"""端到端测试（P5 工程交付硬指标）。

完整链路：导入→搜索→分析→审核→训练→发布→问题卡→回测→导出。

依赖真实基础设施（Docker Compose reviewlens）：PostgreSQL / Elasticsearch /
MinIO / Redis。NLP 服务与 ARQ worker 不常驻，因此：
- NLP 推理/训练做确定性 mock；
- 导入/推理 ARQ 任务改为「同步直接执行」（enqueue 时立即调用任务函数），
  数据仍真实落 PG / ES / MinIO。

运行方式（默认 pytest 已排除 e2e，需显式指定）：
    cd backend && pytest -m e2e
"""
import json

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient

from tests.conftest import TEST_DB_URL

pytestmark = pytest.mark.e2e

PRODUCT_ID = "e2e-product-001"


def _jsonl_line(i: int) -> str:
    rating = [5, 5, 4, 3, 2, 1][i % 6]
    text = (
        f"review {i}: battery life is fine, "
        "shipping was fast, value for money is great overall."
    )
    return json.dumps(
        {
            "review_id": f"e2e-{i}",
            "asin": PRODUCT_ID,
            "title": f"ttl-{i}",
            "text": text,
            "timestamp": 1700000000000 + i,
            "rating": rating,
            "helpful_vote": i,
            "verified_purchase": True,
        }
    )


def _payload(count: int = 210) -> bytes:
    return ("\n".join(_jsonl_line(i) for i in range(count)) + "\n").encode("utf-8")


@pytest.fixture
async def env(monkeypatch):
    """搭建真实运行环境：测试库 + admin + NLP mock + ARQ 任务同步化。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.tasks.import_task as import_task_mod
    import app.tasks.inference_task as inference_task_mod
    from app.core import security
    from app.core.db import get_db
    from app.main import app
    from app.models.base import Base
    from app.models.user import User
    from app.services import dataset_service, nlp_client, prediction_service

    engine = create_async_engine(TEST_DB_URL, pool_pre_ping=True)
    SessionMaker = async_sessionmaker(engine, expire_on_commit=False)

    async def _override_get_db():
        async with SessionMaker() as session:
            yield session

    # 任务层会话与 API 层一致（测试库）
    monkeypatch.setattr(import_task_mod, "AsyncSessionLocal", SessionMaker)
    monkeypatch.setattr(inference_task_mod, "AsyncSessionLocal", SessionMaker)

    # 导入任务：入队即同步执行（无 worker）
    async def _run_import_inline(version: str) -> None:
        await import_task_mod.run_import({}, version)

    monkeypatch.setattr(dataset_service, "enqueue_import", _run_import_inline)

    # 推理任务：入队即同步执行（无 worker）
    async def _run_inference_inline(dataset_version: str, model_version: str | None):
        await inference_task_mod.run_inference({}, dataset_version, model_version)

    monkeypatch.setattr(prediction_service, "enqueue_inference", _run_inference_inline)

    # NLP 确定性 mock
    async def _fake_infer(reviews, model_version=None):
        out = []
        for r in reviews:
            n = int(r["review_id"].split("-")[1])
            sentiment = (
                "positive" if n % 2 == 0 else "neutral" if n % 3 == 0 else "negative"
            )
            out.append(
                {
                    "review_id": r["review_id"],
                    "overall_sentiment": sentiment,
                    "confidence": 0.9,
                    "aspects": [
                        {
                            "aspect": "battery",
                            "sentiment": "negative",
                            "confidence": 0.8,
                        },
                        {
                            "aspect": "shipping",
                            "sentiment": "positive",
                            "confidence": 0.7,
                        },
                    ],
                    "model_version": "e2e-model-v1",
                }
            )
        return out

    async def _fake_train(samples, *, test_size=None, random_seed=None):
        return {
            "model_version": "e2e-model-v1",
            "train_samples": max(len(samples) - 200, 100),
            "test_samples": 1200,  # >= 发布门槛 1000
            "macro_f1": 0.87,  # >= 发布门槛 0.70
            "accuracy": 0.85,
            "classification_report": {},
            "confusion_matrix": {},
            "publish_status": "evaluation_only",
        }

    monkeypatch.setattr(nlp_client, "infer_batch", _fake_infer)
    monkeypatch.setattr(nlp_client, "train_model", _fake_train)

    # 重建表 + 默认分区
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            sa.text(
                "CREATE TABLE IF NOT EXISTS "
                "reviews_default PARTITION OF reviews DEFAULT"
            )
        )

    # 种入 admin 用户（generate/训练/发布需 analyst+，注册默认 operator）
    async with SessionMaker() as db:
        db.add(
            User(
                id="e2e-admin-001",
                email="e2e-admin@example.com",
                password_hash=security.hash_password("Passw0rd!"),
                full_name="E2E Admin",
                role="admin",
            )
        )
        await db.commit()

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, SessionMaker

    app.dependency_overrides.clear()
    await engine.dispose()


async def _login(client) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"email": "e2e-admin@example.com", "password": "Passw0rd!"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_e2e_full_flow(env):
    """导入→搜索→分析→审核→训练→发布→问题卡→回测→导出。"""
    client, _ = env
    token = await _login(client)
    h = _h(token)

    # ---- 1. 导入 ----
    up = await client.post(
        "/api/v1/datasets/imports",
        headers=h,
        files={"file": ("e2e.jsonl", _payload(), "application/octet-stream")},
    )
    assert up.status_code == 202, up.text
    version = up.json()["data"]["dataset_version"]

    # 同步导入已完成：状态 completed，行数 210
    detail = await client.get(f"/api/v1/datasets/{version}", headers=h)
    assert detail.status_code == 200, detail.text
    d = detail.json()["data"]
    assert d["status"] == "completed", d["error_message"]
    assert d["valid_rows"] == 210

    # ---- 2. 搜索（真实 ES）----
    search = await client.post(
        "/api/v1/reviews/search",
        headers=h,
        json={
            "query": "battery",
            "filters": {"dataset_version": version},
            "page_size": 5,
        },
    )
    assert search.status_code == 200, search.text
    assert search.json()["data"]["total"] > 0

    # ---- 3. 分析（触发推理，同步执行）----
    inf = await client.post(
        "/api/v1/predictions/batch",
        headers=h,
        json={"dataset_version": version},
    )
    assert inf.status_code == 202, inf.text
    preds = await client.get(
        f"/api/v1/predictions?dataset_version={version}&page_size=100",
        headers=h,
    )
    assert preds.status_code == 200, preds.text
    assert preds.json()["data"]["total"] == 210

    # ---- 4. 审核（生成任务 + 完成到覆盖率 80%）----
    gen = await client.post(
        "/api/v1/review-tasks/generate",
        headers=h,
        json={"dataset_version": version, "count": 10},
    )
    assert gen.status_code == 201, gen.text
    assert gen.json()["data"]["created"] == 10

    done = 0
    for _ in range(10):
        nxt = await client.get("/api/v1/review-tasks/next", headers=h)
        assert nxt.status_code == 200, nxt.text
        task = nxt.json()["data"]
        if task is None:
            break
        sub = await client.patch(
            f"/api/v1/review-tasks/{task['id']}",
            headers=h,
            json={
                "status": "approved",
                "reviewer_sentiment": task["system_sentiment"],
                "review_reason": "confirm_prediction",
            },
        )
        assert sub.status_code == 200, sub.text
        done += 1
    assert done >= 8  # 需完成 >=80% 覆盖率后才能发布

    summary = await client.get(
        f"/api/v1/review-tasks/summary?dataset_version={version}", headers=h
    )
    assert summary.json()["data"]["completion_rate"] >= 0.8

    # ---- 5. 训练（弱标签）----
    train = await client.post(
        "/api/v1/analysis-runs",
        headers=h,
        json={"dataset_version": version},
    )
    assert train.status_code == 200, train.text
    run_id = train.json()["data"]["id"]
    assert train.json()["data"]["status"] == "succeeded"
    assert train.json()["data"]["macro_f1"] == 0.87

    # ---- 6. 发布 ----
    criteria = await client.get(f"/api/v1/models/{run_id}/criteria", headers=h)
    assert criteria.status_code == 200, criteria.text
    assert criteria.json()["data"]["can_publish"] is True

    pub = await client.post(f"/api/v1/analysis-runs/{run_id}/publish", headers=h)
    assert pub.status_code == 200, pub.text
    cur = await client.get("/api/v1/models/current", headers=h)
    assert cur.json()["data"]["publish_status"] == "published"

    # ---- 7. 问题卡（创建→流转→关闭）----
    issue = await client.post(
        "/api/v1/issues",
        headers=h,
        json={
            "dataset_version": version,
            "title": "e2e 电池问题卡",
            "aspect": "battery",
            "severity": "high",
            "description": "e2e 问题描述",
            "source_review_ids": ["e2e-0"],
        },
    )
    assert issue.status_code == 201, issue.text
    issue_id = issue.json()["data"]["id"]

    # open -> in_progress
    r = await client.patch(
        f"/api/v1/issues/{issue_id}",
        headers=h,
        json={"status": "in_progress", "resolution_note": "开始处置"},
    )
    assert r.status_code == 200, r.text
    # in_progress -> pending_validation
    r = await client.patch(
        f"/api/v1/issues/{issue_id}",
        headers=h,
        json={"status": "pending_validation"},
    )
    assert r.status_code == 200, r.text
    # pending_validation -> closed
    r = await client.patch(
        f"/api/v1/issues/{issue_id}",
        headers=h,
        json={"status": "closed", "validation_note": "已复测达标"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "closed"

    # ---- 8. 回测（真实 ES 聚合）----
    back = await client.post(f"/api/v1/issues/{issue_id}/retrospect", headers=h)
    assert back.status_code == 200, back.text
    data = back.json()["data"]
    assert "pre_rate" in data and "post_rate" in data and "change" in data

    # ---- 9. 导出（真实 MinIO）----
    ex = await client.post(
        "/api/v1/exports",
        headers=h,
        json={"dataset_version": version},
    )
    assert ex.status_code == 201, ex.text
    assert ex.json()["data"]["row_count"] > 0

    exl = await client.get("/api/v1/exports", headers=h)
    assert exl.status_code == 200, exl.text
    assert exl.json()["data"]["total"] >= 1

