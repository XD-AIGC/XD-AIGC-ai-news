"""Tests for theme column on news table."""

from datetime import datetime, timezone

from collectors.base import ContentItem, SourceType, Theme


def test_save_and_load_item_with_theme(temp_db):
    item = ContentItem(
        id="x1",
        source_type=SourceType.RSS,
        title="Fashion news",
        url="https://example.com/1",
        theme=Theme.FASHION,
    )
    temp_db.save_items([item])
    loaded = temp_db.get_items_by_date(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    assert len(loaded) == 1
    assert loaded[0].theme == Theme.FASHION


def test_default_theme_is_ai_for_legacy_rows(temp_db):
    # Insert a row without theme via raw SQL to simulate legacy data
    cursor = temp_db._conn.cursor()
    cursor.execute(
        """INSERT INTO news (id, source_type, title, url, collected_at)
           VALUES (?, ?, ?, ?, ?)""",
        ("legacy1", "rss", "Old item", "https://example.com/old",
         datetime.now(timezone.utc).isoformat()),
    )
    temp_db._conn.commit()

    loaded = temp_db.get_items_by_date(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    assert len(loaded) == 1
    assert loaded[0].theme == Theme.AI
