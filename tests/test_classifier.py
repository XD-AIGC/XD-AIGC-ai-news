"""Tests for theme-scoped KeywordClassifier."""

from collectors.base import ContentItem, SourceType, Theme
from processor.classifier import KeywordClassifier


THEMES = {
    "ai": [
        {"name": "开源模型", "keywords": ["stable diffusion", "flux"]},
        {"name": "ComfyUI", "keywords": ["comfyui"]},
    ],
    "fashion": [
        {"name": "潮流", "keywords": ["streetwear", "hypebeast"]},
        {"name": "时装", "keywords": ["runway", "vogue"]},
    ],
}


def _make_item(title: str, theme: Theme = Theme.AI) -> ContentItem:
    return ContentItem(
        id="x", source_type=SourceType.RSS,
        title=title, url="https://example.com", theme=theme,
    )


def test_ai_item_matches_ai_focus_area():
    c = KeywordClassifier(THEMES)
    item = _make_item("New Stable Diffusion release", Theme.AI)
    result = c.classify(item)
    assert "开源模型" in result


def test_ai_item_does_not_match_fashion_focus_area():
    # Even if title contains "streetwear", AI item stays in AI theme
    c = KeywordClassifier(THEMES)
    item = _make_item("AI generated streetwear designs", Theme.AI)
    result = c.classify(item)
    # Should NOT contain fashion categories
    assert "潮流" not in result


def test_fashion_item_matches_fashion_focus_area():
    c = KeywordClassifier(THEMES)
    item = _make_item("New Vogue runway report", Theme.FASHION)
    result = c.classify(item)
    assert "时装" in result


def test_fashion_item_does_not_match_ai_focus_area():
    c = KeywordClassifier(THEMES)
    item = _make_item("Fashion with stable diffusion tools", Theme.FASHION)
    result = c.classify(item)
    assert "开源模型" not in result


def test_no_match_falls_back_to_qita():
    c = KeywordClassifier(THEMES)
    item = _make_item("Totally unrelated content", Theme.AI)
    result = c.classify(item)
    assert result == ["其他"]


def test_filter_relevant_excludes_qita():
    c = KeywordClassifier(THEMES)
    items = [
        _make_item("Stable Diffusion release", Theme.AI),
        _make_item("Unrelated random text", Theme.AI),
    ]
    filtered = c.filter_relevant(items)
    assert len(filtered) == 1
    assert filtered[0].title == "Stable Diffusion release"
