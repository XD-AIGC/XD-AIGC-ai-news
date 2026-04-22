"""Tests for get_available_dates(theme=...) filtering."""

from datetime import datetime

from collectors.base import ContentItem, SourceType, Theme


def _item(idx: int, theme: Theme, day: str) -> ContentItem:
    return ContentItem(
        id=f"i{idx}",
        source_type=SourceType.RSS,
        title=f"item {idx}",
        url=f"https://example.com/{idx}",
        theme=theme,
        collected_at=datetime.fromisoformat(f"{day}T12:00:00+00:00"),
    )


def test_dates_no_theme_returns_all(temp_db):
    temp_db.save_items([
        _item(1, Theme.AI, "2026-04-22"),
        _item(2, Theme.AI, "2026-04-21"),
        _item(3, Theme.FASHION, "2026-04-22"),
    ])
    rows = temp_db.get_available_dates()
    by_date = {r["date"]: r["count"] for r in rows}
    assert by_date["2026-04-22"] == 2
    assert by_date["2026-04-21"] == 1


def test_dates_theme_fashion_filters(temp_db):
    temp_db.save_items([
        _item(1, Theme.AI, "2026-04-22"),
        _item(2, Theme.AI, "2026-04-22"),
        _item(3, Theme.FASHION, "2026-04-22"),
        _item(4, Theme.FASHION, "2026-04-21"),
    ])
    rows = temp_db.get_available_dates(theme="fashion")
    by_date = {r["date"]: r["count"] for r in rows}
    assert by_date == {"2026-04-22": 1, "2026-04-21": 1}


def test_dates_theme_ai_filters(temp_db):
    temp_db.save_items([
        _item(1, Theme.AI, "2026-04-22"),
        _item(2, Theme.FASHION, "2026-04-22"),
        _item(3, Theme.FASHION, "2026-04-21"),
    ])
    rows = temp_db.get_available_dates(theme="ai")
    by_date = {r["date"]: r["count"] for r in rows}
    assert by_date == {"2026-04-22": 1}


def test_dates_theme_with_no_matches_returns_empty(temp_db):
    temp_db.save_items([_item(1, Theme.AI, "2026-04-22")])
    rows = temp_db.get_available_dates(theme="fashion")
    assert rows == []
