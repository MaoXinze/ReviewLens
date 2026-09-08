"""文本预处理：清洗 + 中文分词（jieba）。

- clean：去空白、统一小写、压缩多余空白、截断超长文本。
- tokenize：jieba 分词保留字母/数字/汉字词元（过滤纯标点)。
维度对齐基线 TF-IDF 的 char_wb analyzer，中英混合评论均可用。
"""
import re

import jieba

_WHITESPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"^[\w\u4e00-\u9fff]+$")
MAX_TEXT_LENGTH = 5000


def clean(text: str, max_length: int = MAX_TEXT_LENGTH) -> str:
    """清洗评论文本：去首尾+压缩空白+小写+截断。"""
    if not text:
        return ""
    cleaned = _WHITESPACE_RE.sub(" ", text).strip().lower()
    return cleaned[:max_length]


def tokenize(text: str) -> list[str]:
    """jieba 分词，过滤纯标点/空白词元。"""
    tokens = jieba.lcut(text)
    return [t for t in tokens if t.strip() and _TOKEN_RE.match(t)]