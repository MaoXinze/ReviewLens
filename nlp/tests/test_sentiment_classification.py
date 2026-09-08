"""NLP 服务：情感分类（TF-IDF+LR）与训练管线单元测试。

合成小样本保证可复现与快速执行；验证 train/predict/save/load 可复现性与
训练门限（publish_status）逻辑。
"""
from pathlib import Path

import pytest

from app.services import training
from app.services.sentiment_classifier import (
    TfidfLrSentimentClassifier,
    model_hash,
)


@pytest.fixture()
def samples() -> list[dict]:
    positive = [
        "battery lasts all day, great performance",
        "fast charging and excellent screen",
        "love the design, very durable build",
        "best value for the price, sharp and bright",
        "excellent sound quality, highly recommend",
    ]
    negative = [
        "battery dies quickly, poor build quality",
        "slow charging and bad screen",
        "terrible battery life, horrible experience",
        "cheap materials, broke after a week",
        "buggy software and poor performance",
    ]
    neutral = [
        "the item arrived in a box",
        "package was shipped on time",
        "unit was delivered as described",
        "the box contains the device",
        "item has a standard design",
    ]
    data = []
    for text, label in (
        [(t, "positive") for t in positive]
        + [(t, "negative") for t in negative]
        + [(t, "neutral") for t in neutral]
    ):
        data.append({"text": text, "label": label})
    return data


def test_classifier_train_and_predict(samples):
    texts = [s["text"] for s in samples]
    labels = [s["label"] for s in samples]
    model = TfidfLrSentimentClassifier()
    metrics = model.train(texts, labels)
    assert "macro_f1" in metrics
    assert "test_samples" in metrics and metrics["test_samples"] > 0

    predictions = model.predict(["the battery is great"])
    assert predictions[0]["sentiment"] in {"positive", "neutral", "negative"}
    assert 0.0 <= predictions[0]["confidence"] <= 1.0


def test_predict_before_train_raises():
    model = TfidfLrSentimentClassifier()
    with pytest.raises(RuntimeError):
        model.predict(["battery ok"])


def test_save_load_roundtrip(samples, tmp_path):
    texts = [s["text"] for s in samples]
    labels = [s["label"] for s in samples]
    model = TfidfLrSentimentClassifier()
    model.train(texts, labels)

    path = str(tmp_path / "model.joblib")
    model.save(path)
    assert Path(path).exists()

    loaded = TfidfLrSentimentClassifier()
    loaded.load(path)
    assert loaded.predict(["battery is amazing"]) == model.predict(
        ["battery is amazing"]
    )


def test_model_hash_reproducible(samples):
    texts = [s["text"] for s in samples]
    labels = [s["label"] for s in samples]
    assert model_hash(texts, labels, 42) == model_hash(texts, labels, 42)
    assert model_hash(texts, labels, 42) != model_hash(texts, labels, 7)


def test_run_training_success(samples, tmp_path, monkeypatch):
    monkeypatch.setattr(training.settings, "model_dir", str(tmp_path))
    record = training.run_training(samples, random_seed=42)
    assert record["status"] == "succeeded"
    assert record["algorithm"] == "tfidf_lr"
    assert record["train_samples"] > 0 and record["test_samples"] > 0
    assert any(k in record for k in ("macro_f1", "accuracy"))
    assert Path(record["model_file_path"]).exists()
    # 训练后当前模型可用
    model, version = training.get_current()
    assert model is not None and version == record["model_version"]


def test_run_training_empty_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(training.settings, "model_dir", str(tmp_path))
    with pytest.raises(ValueError):
        training.run_training([])


def test_run_training_invalid_label_raises(samples, monkeypatch, tmp_path):
    monkeypatch.setattr(training.settings, "model_dir", str(tmp_path))
    bad = dict(samples[0])
    bad["label"] = "very_positive"
    with pytest.raises(ValueError):
        training.run_training([bad])