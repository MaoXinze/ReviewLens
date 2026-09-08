"""DistilBERT 情感三分类微调器（P7/M11 模型增强层）。

- 底座：distilbert-base-uncased（6600 万参数，CPU/GPU 均可训练）。
- 接口刻意对齐 TfidfLrSentimentClassifier（train/predict/save/load），
  以便实验与分层推理对两类模型统一调用；指标键也与基线一致。
- transformers/torch 为惰性导入：模块被 import 时不触发模型加载，
  只有真正调用 train/predict 时才联网/读盘，避免污染基线路径与测试。
"""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.model_selection import train_test_split

from app.core.config import settings

# 标签编码与基线保持一致
LABEL_ENCODER = {"negative": 0, "neutral": 1, "positive": 2}
LABEL_DECODER = {v: k for k, v in LABEL_ENCODER.items()}
_ID2LABEL = {str(k): v for k, v in LABEL_DECODER.items()}


def _now() -> str:
    return datetime.now(UTC).isoformat()


class DistilBertSentimentClassifier:
    """DistilBERT 情感三分类器（fine-tune 产物）。

    未加载（`load` 未调用）时 predict 将抛 RuntimeError，与基线一致。
    """

    def __init__(
        self,
        model_name_or_path: str | None = None,
        *,
        max_length: int = 128,
        num_labels: int = 3,
        batch_size: int = 32,
        learning_rate: float = 2e-5,
        epochs: int = 2,
        weight_decay: float = 0.01,
    ) -> None:
        # 默认底座路径：优先读本地 models/distilbert-base-uncased（P7 已下载）
        self.model_name_or_path = model_name_or_path or str(
            settings.model_dir + "/distilbert-base-uncased"
        )
        self.max_length = max_length
        self.num_labels = num_labels
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.weight_decay = weight_decay
        self.device = self._detect_device()
        self._model = None
        self._tokenizer = None
        self.meta: dict = {}

    # ---------- 基础设施 ----------

    @staticmethod
    def _detect_device() -> str:
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:  # torch 未安装时兜底 CPU
            return "cpu"

    def _load_backbone(self):
        """加载底座（tokenizer + model）。首次需联网/读盘，之后走缓存。"""
        from transformers import (
            AutoConfig,
            AutoModelForSequenceClassification,
            AutoTokenizer,
        )

        if self._tokenizer is None or self._model is None:
            config = AutoConfig.from_pretrained(
                self.model_name_or_path,
                num_labels=self.num_labels,
                id2label=_ID2LABEL,
                label2id=LABEL_ENCODER,
            )
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name_or_path)
            self._model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name_or_path, config=config
            )
            self._model.to(self.device)
        return self._tokenizer, self._model

    # ---------- 训练 ----------

    def train(
        self,
        texts: list[str],
        labels: list[str],
        *,
        test_size: float | None = None,
        random_seed: int | None = None,
        train_idx: list[int] | None = None,
        test_idx: list[int] | None = None,
    ) -> dict:
        """微调并返回评估指标。返回结构对齐基线（额外含训练耗时/train_samples）。

        默认按 test_size/random_seed 分层切分；当提供 train_idx/test_idx 时使用该固定切分
        （用于 E2 对照实验，隔离「标签来源」变量，保证两路使用同一份持出测试）。
        """
        if len(texts) < 2 or len(texts) != len(labels):
            raise ValueError("训练数据为空或文本/标签长度不一致")
        import torch

        size = settings.default_test_size if test_size is None else test_size
        seed = settings.default_random_seed if random_seed is None else random_seed
        y = [LABEL_ENCODER[l] for l in labels]

        if train_idx is None or test_idx is None:
            # 分层切分，保证与基线同分布
            _, _test_idx = train_test_split(
                range(len(texts)), test_size=size, random_state=seed, stratify=y
            )
            mask = [i not in _test_idx for i in range(len(texts))]
            train_idx = [i for i in range(len(texts)) if mask[i]]
            test_idx = sorted(_test_idx)

        train_texts = [texts[i] for i in train_idx]
        train_labels = [y[i] for i in train_idx]
        test_texts = [texts[i] for i in test_idx]
        test_labels = [y[i] for i in test_idx]

        tokenizer, model = self._load_backbone()
        g = torch.Generator().manual_seed(seed)
        torch.manual_seed(seed)

        train_enc = tokenizer(
            train_texts,
            truncation=True,
            padding=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        test_enc = tokenizer(
            test_texts,
            truncation=True,
            padding=True,
            max_length=self.max_length,
            return_tensors="pt",
        )

        class _Dataset(torch.utils.data.Dataset):
            def __init__(self, enc, labels):
                self.enc = enc
                self.labels = labels

            def __len__(self):
                return len(self.labels)

            def __getitem__(self, i):
                return {
                    "input_ids": self.enc["input_ids"][i],
                    "attention_mask": self.enc["attention_mask"][i],
                    "labels": torch.tensor(self.labels[i], dtype=torch.long),
                }

        train_ds = _Dataset(train_enc, train_labels)
        test_ds = _Dataset(test_enc, test_labels)

        from torch.utils.data import DataLoader

        train_loader = DataLoader(
            train_ds, batch_size=self.batch_size, shuffle=True, generator=g
        )
        test_loader = DataLoader(
            test_ds, batch_size=self.batch_size, shuffle=False
        )

        optimizer = torch.optim.AdamW(
            model.parameters(), lr=self.learning_rate, weight_decay=self.weight_decay
        )
        t0 = time.time()
        model.train()
        for epoch in range(self.epochs):
            for batch in train_loader:
                batch = {k: v.to(self.device) for k, v in batch.items()}
                optimizer.zero_grad()
                outputs = model(**batch)
                loss = outputs.loss
                loss.backward()
                optimizer.step()
        train_seconds = time.time() - t0

        # 评估
        predictions, true_labels = [], []
        model.eval()
        with torch.no_grad():
            for batch in test_loader:
                batch = {k: v.to(self.device) for k, v in batch.items()}
                logits = model(**batch).logits
                preds = logits.argmax(dim=-1).cpu().tolist()
                labels_b = batch["labels"].cpu().tolist()
                predictions.extend(preds)
                true_labels.extend(labels_b)

        metrics = self._score(true_labels, predictions)
        metrics["train_samples"] = len(train_labels)
        metrics["test_samples"] = len(test_labels)
        metrics["train_seconds"] = round(train_seconds, 3)
        metrics["device"] = self.device
        metrics["model_name"] = self.model_name_or_path
        self.meta.update(metrics)
        return metrics

    def _score(self, y_test, y_pred) -> dict:
        """按基线 evaluation 的结构产出指标（JSON 安全）。"""
        labels = sorted(set(y_test) | set(y_pred))
        macro_f1 = float(f1_score(y_test, y_pred, labels=labels, average="macro"))
        accuracy = float(accuracy_score(y_test, y_pred))
        report = classification_report(
            y_test, y_pred, labels=labels, output_dict=True, zero_division=0
        )
        cm = confusion_matrix(y_test, y_pred, labels=labels).tolist()
        prec, rec, f1, _ = precision_recall_fscore_support(
            y_test, y_pred, labels=labels, zero_division=0
        )
        per_class = {
            str(label): {
                "precision": round(float(p), 6),
                "recall": round(float(r), 6),
                "f1": round(float(f), 6),
            }
            for label, p, r, f in zip(labels, prec, rec, f1)
        }
        return {
            "macro_f1": round(macro_f1, 6),
            "accuracy": round(accuracy, 6),
            "classification_report": report,
            "confusion_matrix": cm,
            "per_class": per_class,
        }

    # ---------- 推理 ----------

    def predict(self, texts: list[str]) -> list[dict]:
        """批量预测，返回 [{sentiment, confidence}]，与基线格式一致。"""
        if not texts:
            return []
        self._ensure_loaded()
        import torch

        tokenizer, model = self._tokenizer, self._model
        enc = tokenizer(
            texts,
            truncation=True,
            padding=True,
            max_length=self.max_length,
            return_tensors="pt",
        )
        results = []
        model.eval()
        inputs = {k: v.to(self.device) for k, v in enc.items()}
        with torch.no_grad():
            logits = model(**inputs).logits
        probas = torch.softmax(logits, dim=-1).cpu().numpy()
        for proba in probas:
            idx = int(proba.argmax())
            results.append(
                {
                    "sentiment": LABEL_DECODER[idx],
                    "confidence": round(float(proba[idx]), 6),
                }
            )
        return results

    # ---------- 持久化 ----------

    def save(self, path: str) -> str:
        """将微调后的 tokenizer+model 与元数据保存到 path，返回 path。"""
        self._ensure_loaded()
        out = Path(path)
        out.mkdir(parents=True, exist_ok=True)
        self._tokenizer.save_pretrained(str(out))
        self._model.save_pretrained(str(out))
        meta = dict(self.meta)
        meta["saved_at"] = _now()
        with (out / "meta.json").open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return str(out)

    def load(self, path: str) -> None:
        """从 path 加载微调产物（tokenizer + model + meta）。"""
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        p = Path(path)
        self._tokenizer = AutoTokenizer.from_pretrained(str(p))
        config = None
        from transformers import AutoConfig

        config = AutoConfig.from_pretrained(str(p))
        if config.num_labels != self.num_labels:
            config.num_labels = self.num_labels
            config.id2label = _ID2LABEL
            config.label2id = LABEL_ENCODER
        self._model = AutoModelForSequenceClassification.from_pretrained(
            str(p), config=config
        )
        self._model.to(self.device)
        self.meta = {}
        meta_path = p / "meta.json"
        if meta_path.exists():
            self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.model_name_or_path = str(p)

    def _ensure_loaded(self) -> None:
        if self._model is None or self._tokenizer is None:
            raise RuntimeError("模型未加载（distilbert），无法预测")