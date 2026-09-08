"""M5 人工审核工作流测试。

覆盖：
- 生成：从预测结果生成审核任务、重复生成跳过、未知数据集 400、角色限制 403
- 连续审核：/next 返回 pending 任务
- 状态机：pending→approved→verified / rejected，非法流转 400
- 审计轨迹：提交后 review_task_history 有记录
- summary：总任务数 / 完成率 / 一致率
依赖 conftest 的真实 PG 测试库。
"""
import os
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import create_access_token, hash_password
from app.models.dataset import Dataset
from app.models.prediction import ReviewPrediction
from app.models.review import Review
from app.models.user import User

# conftest 在加载时会设置 TEST_DATABASE_URL
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://reviewlens:reviewlens_dev_only@localhost:15432/reviewlens_test",
)

DS = "ds-v1"
MODEL = "m-v1"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed(client, *, with_preds: bool = True) -> dict:
    """向测试库写入 operator/analyst 用户 + 预测 + 评论，返回 token。"""
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

            if with_preds:
                # 数据集（reviews 外键依赖；评论 ID 引用之）
                s.add(
                    Dataset(
                        id=str(uuid4()),
                        dataset_version=DS,
                        source_filename="amazon_reviews.jsonl",
                        file_sha256="x" * 64,
                        storage_path="datasets/ds-v1.jsonl",
                        field_mapping={"rating": "rating", "text": "review_text"},
                        status="completed",
                    )
                )

                # 覆盖三种采样组：低置信度 / 高风险差评 / 随机
                preds = [
                    ReviewPrediction(
                        id=str(uuid4()),
                        dataset_version=DS,
                        review_id="R-low",
                        model_version=MODEL,
                        overall_sentiment="neutral",
                        confidence=0.45,
                        aspects=[],
                    ),
                    ReviewPrediction(
                        id=str(uuid4()),
                        dataset_version=DS,
                        review_id="R-risk",
                        model_version=MODEL,
                        overall_sentiment="negative",
                        confidence=0.90,
                        aspects=[{"aspect": "电池", "sentiment": "negative"}],
                    ),
                    ReviewPrediction(
                        id=str(uuid4()),
                        dataset_version=DS,
                        review_id="R-random",
                        model_version=MODEL,
                        overall_sentiment="positive",
                        confidence=0.92,
                        aspects=[{"aspect": "屏幕", "sentiment": "positive"}],
                    ),
                ]
                for p in preds:
                    s.add(p)

                # 一条评论供审核引用（走 DEFAULT 分区）
                s.add(
                    Review(
                        id=str(uuid4()),
                        dataset_version=DS,
                        review_id="R-risk",
                        product_id="P1",
                        review_text="电池耗电太快，非常失望。",
                        rating=1,
                        reviewed_at=_now(),
                        helpful_votes=2,
                        verified_purchase=True,
                        language="zh",
                    )
                )

            await s.commit()
            operator_id = operator.id
            analyst_id = analyst.id
    finally:
        await engine.dispose()

    return {
        "operator_token": create_access_token(operator_id, "operator"),
        "analyst_token": create_access_token(analyst_id, "analyst"),
    }


# ---------- 纯函数：采样组 ----------
from app.models.review_task import (  # noqa: E402
    SAMPLE_GROUP_HIGH_RISK,
    SAMPLE_GROUP_LOW_CONFIDENCE,
    SAMPLE_GROUP_RANDOM,
)
from app.services import review_task_service  # noqa: E402


class _FakePred:
    def __init__(self, conf, sentiment):
        self.confidence = conf
        self.overall_sentiment = sentiment


def test_sampling_group_low_confidence():
    group, _ = review_task_service._sampling_group_of(_FakePred(0.4, "positive"))
    assert group == SAMPLE_GROUP_LOW_CONFIDENCE


def test_sampling_group_high_risk():
    group, _ = review_task_service._sampling_group_of(_FakePred(0.9, "negative"))
    assert group == SAMPLE_GROUP_HIGH_RISK


def test_sampling_group_random():
    group, _ = review_task_service._sampling_group_of(_FakePred(0.9, "neutral"))
    assert group == SAMPLE_GROUP_RANDOM


# ---------- 生成 ----------


async def test_generate_tasks(client):
    data = await _seed(client)
    resp = await client.post(
        "/api/v1/review-tasks/generate",
        json={"dataset_version": DS, "model_version": MODEL, "count": 10},
        headers=_headers(data["analyst_token"]),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["created"] == 3


async def test_generate_tasks_skips_existing(client):
    data = await _seed(client)
    headers = _headers(data["analyst_token"])
    await client.post(
        "/api/v1/review-tasks/generate",
        json={"dataset_version": DS, "model_version": MODEL, "count": 3},
        headers=headers,
    )
    resp = await client.post(
        "/api/v1/review-tasks/generate",
        json={"dataset_version": DS, "model_version": MODEL, "count": 3},
        headers=headers,
    )
    body = resp.json()
    assert body["data"]["created"] == 0
    assert body["data"]["skipped"] == 3


async def test_generate_requires_analyst(client):
    data = await _seed(client)
    resp = await client.post(
        "/api/v1/review-tasks/generate",
        json={"dataset_version": DS, "model_version": MODEL, "count": 3},
        headers=_headers(data["operator_token"]),
    )
    assert resp.status_code == 403


async def test_generate_unknown_dataset_400(client):
    data = await _seed(client)
    resp = await client.post(
        "/api/v1/review-tasks/generate",
        json={"dataset_version": "ds-missing", "count": 3},
        headers=_headers(data["analyst_token"]),
    )
    assert resp.status_code == 400


async def test_generate_respects_count_cap(client):
    data = await _seed(client)
    resp = await client.post(
        "/api/v1/review-tasks/generate",
        json={"dataset_version": DS, "model_version": MODEL, "count": 2},
        headers=_headers(data["analyst_token"]),
    )
    body = resp.json()
    assert body["data"]["created"] == 2
    # 列表总数为 2，说明 count 上限生效（有 3 条预测）
    lst = await client.get(
        "/api/v1/review-tasks", headers=_headers(data["operator_token"])
    )
    assert lst.json()["data"]["total"] == 2


async def test_list_filter_by_status_and_group(client):
    data = await _seed(client)
    await client.post(
        "/api/v1/review-tasks/generate",
        json={"dataset_version": DS, "count": 3},
        headers=_headers(data["analyst_token"]),
    )
    operator_headers = _headers(data["operator_token"])
    # 按状态筛选
    pending = await client.get(
        "/api/v1/review-tasks?status=pending", headers=operator_headers
    )
    assert pending.json()["data"]["total"] == 3
    # 按采样组筛选：应存在 low_confidence
    low_conf = await client.get(
        "/api/v1/review-tasks?sampling_group=low_confidence", headers=operator_headers
    )
    assert low_conf.json()["data"]["total"] == 1


# ---------- 连续审核 + 状态机 ----------


async def _one_pending_task(client, headers: dict) -> str:
    next_resp = await client.get("/api/v1/review-tasks/next", headers=headers)
    body = next_resp.json()["data"]
    assert body is not None
    assert body["status"] == "pending"
    return body["id"]


async def test_next_returns_pending(client):
    data = await _seed(client)
    await client.post(
        "/api/v1/review-tasks/generate",
        json={"dataset_version": DS, "count": 3},
        headers=_headers(data["analyst_token"]),
    )
    op_headers = _headers(data["operator_token"])
    resp = await client.get("/api/v1/review-tasks/next", headers=op_headers)
    body = resp.json()["data"]
    assert body is not None
    assert body["status"] == "pending"
    assert body["review_id"]


async def test_submit_approve_then_second_review(client):
    data = await _seed(client)
    operator_headers = _headers(data["operator_token"])
    analyst_headers = _headers(data["analyst_token"])
    await client.post(
        "/api/v1/review-tasks/generate",
        json={"dataset_version": DS, "count": 3},
        headers=analyst_headers,
    )
    task_id = await _one_pending_task(client, operator_headers)

    resp = await client.patch(
        f"/api/v1/review-tasks/{task_id}",
        json={
            "status": "approved",
            "reviewer_sentiment": "neutral",
            "review_reason": "confirm_prediction",
        },
        headers=operator_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "approved"

    resp2 = await client.post(
        f"/api/v1/review-tasks/{task_id}/second-review",
        json={"status": "approved", "review_note": "确认无误"},
        headers=analyst_headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["status"] == "verified"


async def test_submit_already_reviewed_400(client):
    data = await _seed(client)
    operator_headers = _headers(data["operator_token"])
    await client.post(
        "/api/v1/review-tasks/generate",
        json={"dataset_version": DS, "count": 3},
        headers=_headers(data["analyst_token"]),
    )
    task_id = await _one_pending_task(client, operator_headers)
    await client.patch(
        f"/api/v1/review-tasks/{task_id}",
        json={"status": "approved", "reviewer_sentiment": "positive"},
        headers=operator_headers,
    )
    resp = await client.patch(
        f"/api/v1/review-tasks/{task_id}",
        json={"status": "approved", "reviewer_sentiment": "positive"},
        headers=operator_headers,
    )
    assert resp.status_code == 400


async def test_second_review_rejects_pending_400(client):
    data = await _seed(client)
    operator_headers = _headers(data["operator_token"])
    await client.post(
        "/api/v1/review-tasks/generate",
        json={"dataset_version": DS, "count": 3},
        headers=_headers(data["analyst_token"]),
    )
    task_id = await _one_pending_task(client, operator_headers)
    resp = await client.post(
        f"/api/v1/review-tasks/{task_id}/second-review",
        json={"status": "approved"},
        headers=_headers(data["analyst_token"]),
    )
    assert resp.status_code == 400
    assert "approved" in resp.json()["detail"]


async def test_reject_flow(client):
    data = await _seed(client)
    operator_headers = _headers(data["operator_token"])
    await client.post(
        "/api/v1/review-tasks/generate",
        json={"dataset_version": DS, "count": 3},
        headers=_headers(data["analyst_token"]),
    )
    task_id = await _one_pending_task(client, operator_headers)
    resp = await client.patch(
        f"/api/v1/review-tasks/{task_id}",
        json={
            "status": "rejected",
            "review_reason": "invalid_text",
            "review_note": "广告",
        },
        headers=operator_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "rejected"


async def test_unknown_task_404(client):
    data = await _seed(client)
    resp = await client.get(
        "/api/v1/review-tasks/not-exist", headers=_headers(data["operator_token"])
    )
    assert resp.status_code == 404


# ---------- 历史轨迹 ----------


async def test_history_recorded_on_submit(client):
    data = await _seed(client)
    operator_headers = _headers(data["operator_token"])
    await client.post(
        "/api/v1/review-tasks/generate",
        json={"dataset_version": DS, "count": 3},
        headers=_headers(data["analyst_token"]),
    )
    task_id = await _one_pending_task(client, operator_headers)
    await client.patch(
        f"/api/v1/review-tasks/{task_id}",
        json={
            "status": "approved",
            "reviewer_sentiment": "neutral",
            "review_note": "ok",
        },
        headers=operator_headers,
    )

    from app.models.review_task import ReviewTaskHistory

    engine = create_async_engine(TEST_DB_URL)
    try:
        session = async_sessionmaker(engine, expire_on_commit=False)
        async with session() as s:
            rows = (
                await s.execute(
                    select(ReviewTaskHistory).where(
                        ReviewTaskHistory.task_id == task_id
                    )
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    assert any(r.field_name == "status" for r in rows)
    assert any(r.field_name == "reviewer_sentiment" for r in rows)
    assert any(r.field_name == "review_note" for r in rows)


# ---------- summary ----------


async def test_summary_zero(client):
    data = await _seed(client, with_preds=False)
    resp = await client.get(
        "/api/v1/review-tasks/summary",
        headers=_headers(data["operator_token"]),
    )
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["total"] == 0
    assert body["completion_rate"] == 0.0


async def test_summary_counts_and_rates(client):
    data = await _seed(client)
    operator_headers = _headers(data["operator_token"])
    analyst_headers = _headers(data["analyst_token"])
    await client.post(
        "/api/v1/review-tasks/generate",
        json={"dataset_version": DS, "count": 3},
        headers=analyst_headers,
    )
    task_id = await _one_pending_task(client, operator_headers)
    await client.patch(
        f"/api/v1/review-tasks/{task_id}",
        json={"status": "approved", "reviewer_sentiment": "neutral"},
        headers=operator_headers,
    )

    resp = await client.get(
        "/api/v1/review-tasks/summary?dataset_version=ds-v1", headers=operator_headers
    )
    body = resp.json()["data"]
    assert body["total"] == 3
    assert body["done"] == 1
    assert body["pending"] == 2
    assert body["approved"] == 1
    assert body["completion_rate"] == round(1 / 3, 4)
    # 该任务 system 为 neutral 且 reviewer 选了 neutral → 一致率 1.0
    assert body["agreement_rate"] == 1.0


async def test_summary_agreement_mismatch(client):
    data = await _seed(client)
    operator_headers = _headers(data["operator_token"])
    await client.post(
        "/api/v1/review-tasks/generate",
        json={"dataset_version": DS, "count": 3},
        headers=_headers(data["analyst_token"]),
    )
    task_id = await _one_pending_task(client, operator_headers)
    await client.patch(
        f"/api/v1/review-tasks/{task_id}",
        json={"status": "approved", "reviewer_sentiment": "positive"},
        headers=operator_headers,
    )
    resp = await client.get("/api/v1/review-tasks/summary", headers=operator_headers)
    body = resp.json()["data"]
    # 第一条任务 system_sentiment 为 neutral，reviewer 选了 positive → 不一致
    assert body["agreement_rate"] == 0.0
