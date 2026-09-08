"""训练管线：训练 TF-IDF+LR → 落盘模型 → 记录运行/模型元数据。

- 训练数据为 {text, label} 样本数组；label ∈ {positive, neutral, negative}。
- model_version 由「训练数据 + seed」哈希生成，保证可复现（同数据同 seed 同版本）。
- 运行/模型元数据与 current 指针持久化到 model_dir/training_state.json，
  服务重启后自动恢复（内存态仅作缓存），避免推理静默降级为规则启发。
"""
import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.services.sentiment_classifier import (
    LABEL_ENCODER,
    TfidfLrSentimentClassifier,
    model_hash,
)

logger = logging.getLogger(__name__)

_runs: dict[str, dict] = {}
_models: dict[str, dict] = {}
# 当前生产模型（最新一次成功训练）
_current: TfidfLrSentimentClassifier | None = None
_current_version: str | None = None

# 元数据落盘文件名与并发锁（训练在线程池中执行，需防并发写坏状态文件）
_STATE_FILE = "training_state.json"
_state_lock = threading.Lock()

_VALID_LABELS = set(LABEL_ENCODER)
_PUBLISH_THRESHOLD = 0.70


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _state_path() -> Path:
    return Path(settings.model_dir) / _STATE_FILE


def _save_state_locked() -> None:
    """把运行元数据 + current 指针写入 model_dir（调用方需持有 _state_lock）。"""
    payload = {
        "runs": _runs,
        "models": _models,
        "current_version": _current_version,
    }
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _restore_current_locked() -> None:
    """按 current_version 从磁盘加载基线模型，恢复内存推理状态。"""
    global _current
    version = _current_version
    if version is None:
        return
    record = _models.get(version)
    path = record.get("model_file_path") if record else None
    if not path or not Path(path).exists():
        logger.warning("训练状态恢复：current 模型文件缺失（%s）", path)
        return
    try:
        model = TfidfLrSentimentClassifier()
        model.load(str(path))
        _current = model
        logger.info("训练状态恢复：已加载 current 模型 %s", version)
    except Exception:  # 恢复失败不阻断启动，推理回退规则启发
        logger.exception("训练状态恢复失败：%s", version)


def _load_state() -> None:
    """从 model_dir 恢复训练元数据与 current 模型（幂等，服务启动时调用）。"""
    global _runs, _models, _current_version
    path = _state_path()
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("训练状态文件损坏，忽略：%s", path)
        return
    with _state_lock:
        _runs = payload.get("runs", {})
        _models = payload.get("models", {})
        _current_version = payload.get("current_version")
        _restore_current_locked()


def _validate_samples(samples: list[dict]) -> None:
    if not samples:
        raise ValueError("训练样本为空")
    for s in samples:
        if "text" not in s or "label" not in s:
            raise ValueError("样本缺少 text 或 label 字段")
        if s["label"] not in _VALID_LABELS:
            raise ValueError(f"非法标签: {s['label']}")


def run_training(
    samples: list[dict], *, test_size: float | None = None, random_seed: int | None = None
) -> dict:
    """训练新模型并返回运行/模型记录；成功后设为当前生产模型。"""
    _validate_samples(samples)
    seed = settings.default_random_seed if random_seed is None else random_seed
    size = settings.default_test_size if test_size is None else test_size

    texts = [s["text"] for s in samples]
    labels = [s["label"] for s in samples]
    version = f"tfidf_lr_{model_hash(texts, labels, seed)}"

    model = TfidfLrSentimentClassifier()
    metrics = model.train(texts, labels, test_size=size, random_seed=seed)

    settings.ensure_dirs()
    model_path = Path(settings.model_dir) / f"{version}.joblib"
    model.save(str(model_path))

    published = metrics["macro_f1"] >= _PUBLISH_THRESHOLD
    record = {
        "model_version": version,
        "algorithm": "tfidf_lr",
        "random_seed": seed,
        "train_samples": metrics["train_samples"],
        "test_samples": metrics["test_samples"],
        "macro_f1": metrics["macro_f1"],
        "accuracy": metrics["accuracy"],
        "classification_report": metrics["classification_report"],
        "confusion_matrix": metrics["confusion_matrix"],
        "per_class": metrics["per_class"],
        "status": "succeeded",
        "publish_status": "published" if published else "evaluation_only",
        "model_file_path": str(model_path),
        "created_at": _now(),
    }
    with _state_lock:
        _runs[version] = record
        _models[version] = record
        _set_current(version, model)
        try:
            _save_state_locked()
        except OSError:
            logger.exception("训练状态落盘失败：%s", version)
    return record


def get_run(run_id: str) -> dict:
    return _runs.get(run_id)


def get_model(version: str) -> dict:
    return _models.get(version)


def _set_current(version: str, model: TfidfLrSentimentClassifier) -> None:
    global _current, _current_version
    _current = model
    _current_version = version


def get_current() -> tuple[TfidfLrSentimentClassifier | None, str | None]:
    return _current, _current_version


# 服务进程启动（模块首次导入）时从磁盘恢复状态
_load_state()
