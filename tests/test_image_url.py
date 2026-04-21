"""Tests for image_url field on ContentItem + news table."""

from datetime import datetime, timezone

from collectors.base import ContentItem, SourceType, Theme


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def test_content_item_default_image_url_is_none():
    item = ContentItem(
        id="x", source_type=SourceType.RSS, title="t", url="u",
    )
    assert item.image_url is None


def test_content_item_accepts_image_url():
    item = ContentItem(
        id="x", source_type=SourceType.RSS, title="t", url="u",
        image_url="https://cdn.example.com/cover.jpg",
    )
    assert item.image_url == "https://cdn.example.com/cover.jpg"


def test_save_and_load_item_with_image_url(temp_db):
    item = ContentItem(
        id="img1",
        source_type=SourceType.RSS,
        title="Fashion shoot",
        url="https://example.com/article-1",
        theme=Theme.FASHION,
        image_url="https://example.com/img/cover-1.jpg",
    )
    temp_db.save_items([item])
    loaded = temp_db.get_items_by_date(_today())
    assert len(loaded) == 1
    assert loaded[0].image_url == "https://example.com/img/cover-1.jpg"


def test_save_and_load_item_without_image_url(temp_db):
    item = ContentItem(
        id="noimg1",
        source_type=SourceType.RSS,
        title="Plain news",
        url="https://example.com/article-2",
        theme=Theme.FASHION,
    )
    temp_db.save_items([item])
    loaded = temp_db.get_items_by_date(_today())
    assert len(loaded) == 1
    assert loaded[0].image_url is None


def test_legacy_row_without_image_url_column_loads(temp_db):
    """Rows inserted via raw SQL without image_url should load with None."""
    cursor = temp_db._conn.cursor()
    cursor.execute(
        """INSERT INTO news (id, source_type, title, url, collected_at)
           VALUES (?, ?, ?, ?, ?)""",
        ("legacy-img", "rss", "Old item", "https://example.com/legacy",
         datetime.now(timezone.utc).isoformat()),
    )
    temp_db._conn.commit()

    loaded = temp_db.get_items_by_date(_today())
    assert len(loaded) == 1
    assert loaded[0].image_url is None
