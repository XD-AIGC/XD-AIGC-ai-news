"""Tests for user_sources CRUD."""

import json

from storage.user_sources import (
    UserSource, compute_url_hash, insert_user_source,
    get_by_url_hash, list_by_status, update_status,
    update_fetch_status,
)


def test_compute_url_hash_normalizes():
    # Same URL with/without trailing slash, fragment → same hash
    assert compute_url_hash("https://example.com/feed") == compute_url_hash("https://example.com/feed/")
    assert compute_url_hash("https://EXAMPLE.com/feed") == compute_url_hash("https://example.com/feed")
    assert compute_url_hash("https://example.com/feed#top") == compute_url_hash("https://example.com/feed")


def test_insert_and_get_user_source(temp_db):
    src = UserSource(
        url="https://hypebeast.com/feed",
        url_hash=compute_url_hash("https://hypebeast.com/feed"),
        status="pending",
        source_type="rss",
        normalized_config=json.dumps({"feed_url": "https://hypebeast.com/feed"}),
        theme="fashion",
        focus_areas=json.dumps(["潮流"]),
        llm_reasoning="...",
        sample_json=json.dumps([]),
        name="Hypebeast",
    )
    sid = insert_user_source(temp_db, src)
    assert sid > 0

    got = get_by_url_hash(temp_db, src.url_hash)
    assert got is not None
    assert got.url == "https://hypebeast.com/feed"
    assert got.theme == "fashion"


def test_update_status_to_active(temp_db):
    src = UserSource(
        url="https://x.com/feed",
        url_hash=compute_url_hash("https://x.com/feed"),
        status="pending",
        source_type="rss",
        normalized_config="{}",
        theme="ai",
        focus_areas="[]",
        llm_reasoning="",
        sample_json="[]",
        name="X",
    )
    sid = insert_user_source(temp_db, src)
    update_status(temp_db, sid, "active")
    got = get_by_url_hash(temp_db, src.url_hash)
    assert got.status == "active"
    assert got.activated_at is not None


def test_list_by_status_returns_only_matching(temp_db):
    for i, status in enumerate(["pending", "active", "active", "rejected"]):
        src = UserSource(
            url=f"https://example.com/{i}",
            url_hash=compute_url_hash(f"https://example.com/{i}"),
            status=status,
            source_type="rss", normalized_config="{}",
            theme="ai", focus_areas="[]",
            llm_reasoning="", sample_json="[]", name=f"S{i}",
        )
        insert_user_source(temp_db, src)

    active = list_by_status(temp_db, "active")
    assert len(active) == 2

    pending = list_by_status(temp_db, "pending")
    assert len(pending) == 1


def test_update_fetch_status_increments_failures(temp_db):
    src = UserSource(
        url="https://flaky.example/feed",
        url_hash=compute_url_hash("https://flaky.example/feed"),
        status="active", source_type="rss", normalized_config="{}",
        theme="ai", focus_areas="[]",
        llm_reasoning="", sample_json="[]", name="Flaky",
    )
    sid = insert_user_source(temp_db, src)

    update_fetch_status(temp_db, sid, "fail:timeout")
    update_fetch_status(temp_db, sid, "fail:timeout")
    got = get_by_url_hash(temp_db, src.url_hash)
    assert got.consecutive_failures == 2

    update_fetch_status(temp_db, sid, "ok")
    got = get_by_url_hash(temp_db, src.url_hash)
    assert got.consecutive_failures == 0
