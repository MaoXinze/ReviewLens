"""M4 预测与训练运行测试。

- 纯函数单测：评分弱标签映射、推理 ORM 转换、发布门槛判断
- API 集成测试：批量推理校验 / 预测查询 / 训练运行触发（使用真实 PG 测试库）
"""
from types import SimpleNamespace

from app.services import analysis_service
from app.tasks.inference_task import _to_orm

# ---------- 纯函数 ----------

def test_rating_to_sentiment():
    assert analysis_service.rating_to_sentiment(5) == "positive"
    assert analysis_service.rating_to_sentiment(4) == "positive"
    assert analysis_service.rating_to_sentiment(3) == "neutral"
    assert analysis_service.rating_to_sentiment(2) == "negative"
    assert analysis_service.rating_to_sentiment(1) == "negative"


def test_inference_to_orm_mapping():
    pred = {
        "review_id": "R1",
        "overall_sentiment": "negative",
        "confidence": 0.62,
        "aspects": [{"aspect": "电池续航", "sentiment": "negative", "confidence": 0.8}],
    }
    orm = _to_orm(pred, "ds-v1", "tfidf_lr_abc")
    assert orm.dataset_version == "ds-v1"
    assert orm.review_id == "R1"
    assert orm.model_version == "tfidf_lr_abc"
    assert orm.overall_sentiment == "negative"
    assert orm.confidence == 0.62
    assert orm.aspects[0]["aspect"] == "电池续航"


def _fake_run(**kw):
    base = dict(
        status="succeeded",
        publish_status="evaluation_only",
        macro_f1=0.8,
        test_samples=1200,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class _FakeDb:
    def __init__(self):
        self.committed = False

    async def commit(self):
        self.committed = True


async def test_publish_run_requires_succeeded():
    run = _fake_run(status="failed")
    try:
        await analysis_service.publish_run(_FakeDb(), run)
        raise AssertionError("应当拒绝未成功完成的训练")
    except ValueError as exc:
        assert "成功" in str(exc)


async def test_publish_run_below_f1_gate():
    run = _fake_run(macro_f1=0.55)
    try:
        await analysis_service.publish_run(_FakeDb(), run)
        raise AssertionError("应当拒绝低于 Macro-F1 门槛")
    except ValueError as exc:
        assert "Macro-F1" in str(exc)


async def test_publish_run_below_test_samples_gate():
    run = _fake_run(test_samples=100)
    try:
        await analysis_service.publish_run(_FakeDb(), run)
        raise AssertionError("应当拒绝测试样本不足")
    except ValueError as exc:
        assert "测试样本" in str(exc)


async def test_publish_run_already_published():
    run = _fake_run(publish_status="published")
    assert await analysis_service.publish_run(_FakeDb(), run) == "模型已是发布状态"


async def test_publish_run_success():
    db = _FakeDb()
    run = _fake_run()
    msg = await analysis_service.publish_run(db, run)
    assert msg == "模型已发布"
    assert run.publish_status == "published"
    assert db.committed


# ---------- API 集成（需 PG 测试库） ----------


async def _auth_headers(client):
    email = "m4@example.com"
    await client.post(
        "/api/auth/register",
        json={"email": email, "password": "Passw0rd!", "full_name": "M4"},
    )
    login = await client.post(
        "/api/auth/login", json={"email": email, "password": "Passw0rd!"}
    )
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_batch_inference_unknown_dataset(client):
    headers = await _auth_headers(client)
    resp = await client.post(
        "/api/v1/predictions/batch",
        json={"dataset_version": "ds-missing"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "不存在" in resp.json()["detail"]


async def test_batch_inference_requires_role(client):
    # 未认证 → 401
    resp = await client.post(
        "/api/v1/predictions/batch", json={"dataset_version": "x"}
    )
    assert resp.status_code == 401


async def test_predictions_list_empty(client):
    headers = await _auth_headers(client)
    resp = await client.get("/api/v1/predictions", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["items"] == []
    assert body["data"]["total"] == 0


async def test_low_confidence_list_empty(client):
    headers = await _auth_headers(client)
    resp = await client.get("/api/v1/predictions/low-confidence", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["items"] == []


async def test_create_analysis_run_insufficient_samples(client):
    headers = await _auth_headers(client)
    resp = await client.post(
        "/api/v1/analysis-runs",
        json={"dataset_version": "ds-missing", "algorithm": "tfidf_lr"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "不足" in resp.json()["detail"]
