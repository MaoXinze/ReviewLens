"""NLP 服务：属性抽取（规则+词表）单元测试。"""
import json

import pytest

from app.services.aspect_extractor import RuleBasedAspectExtractor

TAXONOMY = {
    "电池续航": {"keywords": ["battery", "续航", "电池"]},
    "屏幕显示": {"keywords": ["screen", "屏幕", "显示"]},
}


@pytest.fixture()
def extractor(tmp_path) -> RuleBasedAspectExtractor:
    source = tmp_path / "taxonomy.json"
    source.write_text(json.dumps(TAXONOMY, ensure_ascii=False), encoding="utf-8")
    return RuleBasedAspectExtractor(str(source))


def test_extract_positive_aspect(extractor):
    result = extractor.extract("the battery life is good")
    assert isinstance(result, list)
    assert result[0]["aspect"] == "电池续航"
    assert result[0]["sentiment"] == "positive"
    assert result[0]["confidence"] == 0.7


def test_extract_negative_aspect(extractor):
    result = extractor.extract("battery dies fast, poor quality")
    assert result[0]["aspect"] == "电池续航"
    assert result[0]["sentiment"] == "negative"


def test_extract_multiple_aspects(extractor):
    result = extractor.extract("great screen brightness but the battery is poor")
    aspects = [a["aspect"] for a in result]
    assert "屏幕显示" in aspects
    assert "电池续航" in aspects


def test_extract_neutral_when_no_sentiment_word(extractor):
    result = extractor.extract("battery arrived today")
    assert result[0]["sentiment"] == "neutral"


def test_extract_each_aspect_once(extractor):
    result = extractor.extract("battery battery battery is good")
    assert [a["aspect"] for a in result].count("电池续航") == 1


def test_extract_empty_text(extractor):
    assert extractor.extract("") == []
    assert extractor.extract(None) == []


def test_infer_overall_by_aspect(extractor):
    assert extractor.infer_overall("battery is poor")["sentiment"] == "negative"
    assert extractor.infer_overall("screen is great")["sentiment"] == "positive"
    assert extractor.infer_overall("battery arrived")["sentiment"] == "neutral"