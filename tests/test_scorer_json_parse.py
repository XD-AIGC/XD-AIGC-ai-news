"""Tests for AIScorer._parse_json resilience against common LLM JSON bugs."""

import pytest

from processor.scorer import AIScorer


def test_parse_well_formed_json():
    text = '{"score": 7, "summary": "ok", "categories": ["x"]}'
    out = AIScorer._parse_json(text)
    assert out == {"score": 7, "summary": "ok", "categories": ["x"]}


def test_parse_strips_markdown_fence():
    text = '```json\n{"score": 8, "summary": "fenced"}\n```'
    out = AIScorer._parse_json(text)
    assert out == {"score": 8, "summary": "fenced"}


def test_parse_strips_bare_fence():
    text = '```\n{"score": 5}\n```'
    out = AIScorer._parse_json(text)
    assert out == {"score": 5}


def test_parse_repairs_unescaped_double_quote_in_string():
    """LLM forgets to escape an inner quote — repair should still succeed."""
    text = '{"score": 7, "summary": "He said "hi" today", "categories": ["x"]}'
    out = AIScorer._parse_json(text)
    assert out["score"] == 7
    assert "hi" in out["summary"]
    assert out["categories"] == ["x"]


def test_parse_repairs_trailing_comma():
    text = '{"score": 6, "summary": "ok", "categories": ["x"],}'
    out = AIScorer._parse_json(text)
    assert out["score"] == 6
    assert out["categories"] == ["x"]


def test_parse_repairs_missing_comma():
    text = '{"score": 6 "summary": "ok"}'
    out = AIScorer._parse_json(text)
    assert out["score"] == 6
    assert out["summary"] == "ok"


def test_parse_returns_dict_for_repaired_input():
    """Even after repair, return type must remain a dict for downstream .get() calls."""
    text = '{"score": 7, "summary": "x" "categories": ["y"]}'
    out = AIScorer._parse_json(text)
    assert isinstance(out, dict)


def test_parse_raises_on_unrecoverable_garbage():
    """Total garbage that is not JSON-shaped should raise (not silently return {})."""
    text = "this is just plain prose, not even close to JSON"
    with pytest.raises(Exception):
        AIScorer._parse_json(text)
