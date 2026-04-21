"""Tests for the has_image filter on NewsDatabase.search_items."""

from collectors.base import ContentItem, SourceType, Theme


def _items_in() -> list[ContentItem]:
    return [
        ContentItem(
            id="a", source_type=SourceType.RSS, title="with image",
            url="https://example.com/a", theme=Theme.FASHION,
            image_url="https://example.com/img/a.jpg",
        ),
        ContentItem(
            id="b", source_type=SourceType.RSS, title="no image",
            url="https://example.com/b", theme=Theme.FASHION,
        ),
        ContentItem(
            id="c", source_type=SourceType.RSS, title="empty image",
            url="https://example.com/c", theme=Theme.FASHION,
            image_url="",
        ),
    ]


def test_has_image_true_returns_only_items_with_non_empty_image(temp_db):
    temp_db.save_items(_items_in())
    items, total = temp_db.search_items(theme="fashion", has_image=True)
    assert total == 1
    assert {i.id for i in items} == {"a"}


def test_has_image_false_returns_all_matching_items(temp_db):
    temp_db.save_items(_items_in())
    _, total = temp_db.search_items(theme="fashion", has_image=False)
    assert total == 3


def test_has_image_default_is_false_back_compat(temp_db):
    temp_db.save_items(_items_in())
    _, total = temp_db.search_items(theme="fashion")
    assert total == 3
