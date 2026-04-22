"""Tests for main.py pipeline plumbing — user_source merge dedup +
post-fetch status marking."""

import json

from main import _mark_active_sources_fetched, _merge_user_sources_into_config
from storage.user_sources import UserSource, compute_url_hash, insert_user_source


def _add_active_rss(db, url: str, name: str = "Custom Feed") -> int:
    src = UserSource(
        url=url,
        url_hash=compute_url_hash(url),
        status="active",
        source_type="rss",
        normalized_config=json.dumps({"url": url, "name": name}),
        theme="ai",
        focus_areas="[]",
        llm_reasoning="ok",
        sample_json="[]",
        name=name,
    )
    return insert_user_source(db, src)


def test_merge_dedups_user_source_url_already_in_static_config(temp_db):
    """If a user subscribes to a feed URL already in config.yaml, do NOT add it
    twice — the network would otherwise be hit twice per pipeline run."""
    _add_active_rss(temp_db, url="https://hnrss.org/frontpage")

    config = {
        "sources": {
            "rss": {
                "enabled": True,
                "feeds": [
                    {"url": "https://hnrss.org/frontpage", "name": "HN", "theme": "ai"},
                ],
            }
        }
    }
    merged = _merge_user_sources_into_config(config, temp_db)
    feeds = merged["sources"]["rss"]["feeds"]
    assert len(feeds) == 1, "duplicate URL should not be appended"


def test_merge_appends_user_source_with_new_url(temp_db):
    _add_active_rss(temp_db, url="https://example.com/unique.xml", name="Unique")

    config = {
        "sources": {
            "rss": {
                "enabled": True,
                "feeds": [
                    {"url": "https://hnrss.org/frontpage", "name": "HN", "theme": "ai"},
                ],
            }
        }
    }
    merged = _merge_user_sources_into_config(config, temp_db)
    urls = [f["url"] for f in merged["sources"]["rss"]["feeds"]]
    assert "https://example.com/unique.xml" in urls
    assert len(merged["sources"]["rss"]["feeds"]) == 2


def test_mark_active_sources_fetched_writes_ok_to_each(temp_db):
    """After a pipeline run, every active source should have
    last_fetch_status='ok' and a non-null last_fetch_at."""
    sid1 = _add_active_rss(temp_db, "https://e.com/a.xml", "A")
    sid2 = _add_active_rss(temp_db, "https://e.com/b.xml", "B")

    _mark_active_sources_fetched(temp_db, status="ok")

    rows = list(temp_db._conn.execute(
        "SELECT id, last_fetch_status, last_fetch_at FROM user_sources WHERE id IN (?, ?)",
        (sid1, sid2),
    ))
    assert all(r["last_fetch_status"] == "ok" for r in rows)
    assert all(r["last_fetch_at"] for r in rows)
