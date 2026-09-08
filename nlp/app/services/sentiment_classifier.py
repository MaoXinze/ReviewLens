"""TF-IDF + Logistic Regression 情感分类基线（M4）。

- analyzer='char_wb' 混合中英字符级 n-gram，对中文评论更鲁棒。
- class_weight='balanced' 缓解类别不平衡（负面评论通常偏少）。
- 提供 train/evaluate/predict/save/load，指标可复现（random_seed=42）。
"""
import hashlib

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

from app.core.config import settings
from app.services.evaluation import evaluate

# 标签编码：字符串 -> 数值
LABEL_ENCODER = {"negative": 0, "neutral": 1, "positive": 2}
LABEL_DECODER = {v: k for k, v in LABEL_ENCODER.items()}


class TfidfLrSentimentClassifier:
    """TF-IDF + 逻辑回归的情感三分类器。

    predict 依赖已训练模型；未训练时调用将抛 RuntimeError。
    """

    def __init__(self) -> None:
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            max_features=settings.tfidf_max_features,
            analyzer="char_wb",
        )
        self.classifier = LogisticRegression(
            C=settings.lr_c,
            max_iter=settings.lr_max_iter,
            class_weight="balanced",
            random_state=settings.default_random_seed,
        )

    def train(
        self,
        texts: list[str],
        labels: list[str],
        *,
        test_size: float | None = None,
        random_seed: int | None = None,
    ) -> dict:
        """训练并返回评估指标。要求 labels 至少覆盖 2 个类别才可分层切分。"""
        if len(texts) < 2 or len(texts) != len(labels):
            raise ValueError("训练数据为空或文本/标签长度不一致")
        size = settings.default_test_size if test_size is None else test_size
        seed = settings.default_random_seed if random_seed is None else random_seed
        y = [LABEL_ENCODER[l] for l in labels]

        X = self.vectorizer.fit_transform(texts)
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=size, random_state=seed, stratify=y
        )
        self.classifier.fit(X_train, y_train)
        metrics = evaluate(self, X_test, y_test)
        metrics["train_samples"] = len(y_train)
        metrics["test_samples"] = len(y_test)
        return metrics

    def predict(self, texts: list[str]) -> list[dict]:
        """批量预测，返回 [{sentiment, confidence}]。"""
        if not texts:
            return []
        self._ensure_trained()
        X = self.vectorizer.transform(texts)
        probas = self.classifier.predict_proba(X)
        predictions = []
        for proba in probas:
            idx = int(proba.argmax())
            predictions.append(
                {
                    "sentiment": LABEL_DECODER[idx],
                    "confidence": round(float(proba[idx]), 6),
                }
            )
        return predictions

    def _ensure_trained(self) -> None:
        if not getattr(self, "classifier", None) or not hasattr(
            self.classifier, "classes_"
        ):
            raise RuntimeError("模型未训练，无法预测")

    def save(self, path: str) -> None:
        """持久化模型到 path。"""
        joblib.dump(
            {"vectorizer": self.vectorizer, "classifier": self.classifier}, path
        )

    def load(self, path: str) -> None:
        """从 path 加载模型。"""
        data = joblib.load(path)
        self.vectorizer = data["vectorizer"]
        self.classifier = data["classifier"]


def model_hash(texts: list[str], labels: list[str], seed: int) -> str:
    """基于训练数据 + seed 生成稳定的模型版本号（可复现训练）。"""
    joined = "\x1f".join(f"{t}\x1e{l}" for t, l in zip(texts, labels))
    return hashlib.sha256(f"{seed}:{joined}".encode()).hexdigest()[:12]