"""模型评测：基于数值编码 y_true 计算宏观指标。

y_true/y_pred 为数值编码(0=negative,1=neutral,2=positive)。输出指标字典，
classification_report 与 confusion_matrix 序列化为可 JSON 入库的结构（基本类型）。
"""
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)


def _labels_in(value) -> list[int]:
    return sorted(int(x) for x in value)


def evaluate(classifier, X_test, y_test: list[int]) -> dict:
    """用已训练分类器在测试集上评测，返回指标字典。"""
    y_pred = [int(p) for p in classifier.classifier.predict(X_test)]
    labels = _labels_in(classifier.classifier.classes_)

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