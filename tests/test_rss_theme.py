"""Tests for RSSCollector propagating per-feed theme into ContentItem."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from collectors.base import Theme
from collectors.rss_collector import RSSCollector


@pytest.mark.asyncio
async def test_rss_propagates_feed_theme_to_items(monkeypatch):
    sample_rss = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <title>Test Feed</title>
      <item>
        <title>Hello</title>
        <link>https://example.com/1</link>
        <pubDate>Mon, 21 Apr 2026 10:00:00 +0000</pubDate>
      </item>
    </channel></rss>"""

    client = AsyncMock()
    response = MagicMock()
    response.text = sample_rss
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    feeds = [
        {"url": "https://hypebeast.com/feed", "name": "Hypebeast", "theme": "fashion"},
    ]
    collector = RSSCollector(feeds, client)

    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    items = await collector.fetch(since)

    assert len(items) == 1
    assert items[0].theme == Theme.FASHION


@pytest.mark.asyncio
async def test_rss_defaults_to_ai_when_theme_not_set(monkeypatch):
    sample_rss = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title>Hello</title>
        <link>https://example.com/1</link>
        <pubDate>Mon, 21 Apr 2026 10:00:00 +0000</pubDate>
      </item>
    </channel></rss>"""

    client = AsyncMock()
    response = MagicMock()
    response.text = sample_rss
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    feeds = [{"url": "https://openai.com/blog/rss.xml", "name": "OpenAI"}]
    collector = RSSCollector(feeds, client)
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    items = await collector.fetch(since)

    assert items[0].theme == Theme.AI
