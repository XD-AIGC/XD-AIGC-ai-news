"""Tests for ContentItem theme field."""

from collectors.base import ContentItem, SourceType, Theme


def test_content_item_theme_defaults_to_ai():
    item = ContentItem(
        id="x", source_type=SourceType.RSS,
        title="T", url="https://example.com",
    )
    assert item.theme == Theme.AI


def test_content_item_accepts_fashion_theme():
    item = ContentItem(
        id="x", source_type=SourceType.RSS,
        title="T", url="https://example.com",
        theme=Theme.FASHION,
    )
    assert item.theme == Theme.FASHION


def test_theme_enum_values():
    assert Theme.AI.value == "ai"
    assert Theme.FASHION.value == "fashion"
