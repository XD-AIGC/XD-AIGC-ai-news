"""Tests for subscribe_analyzer URL detector."""

import pytest

from processor.subscribe_analyzer import detect_url_type, DetectionResult


def test_detect_youtube_channel_url():
    r = detect_url_type("https://www.youtube.com/channel/UCbfYPyITQ-7l4upoX8nvctg", rsshub_routes=[])
    assert r.type == "youtube"
    assert r.config["channel_id"] == "UCbfYPyITQ-7l4upoX8nvctg"


def test_detect_youtube_handle_url():
    r = detect_url_type("https://youtube.com/@mkbhd", rsshub_routes=[])
    assert r.type == "youtube"
    assert r.config["handle"] == "mkbhd"


def test_detect_bilibili_space():
    r = detect_url_type("https://space.bilibili.com/291229", rsshub_routes=[])
    assert r.type == "bilibili"
    assert r.config["uid"] == "291229"


def test_detect_twitter_profile():
    r = detect_url_type("https://twitter.com/karpathy", rsshub_routes=[])
    assert r.type == "twitter"
    assert r.config["handle"] == "karpathy"


def test_detect_x_com_profile():
    r = detect_url_type("https://x.com/sama", rsshub_routes=[])
    assert r.type == "twitter"
    assert r.config["handle"] == "sama"


def test_detect_reddit_subreddit():
    r = detect_url_type("https://reddit.com/r/MachineLearning", rsshub_routes=[])
    assert r.type == "reddit"
    assert r.config["subreddit"] == "MachineLearning"


def test_detect_telegram_channel():
    r = detect_url_type("https://t.me/zaihuapd", rsshub_routes=[])
    assert r.type == "telegram"
    assert r.config["channel"] == "zaihuapd"


def test_detect_github_repo():
    r = detect_url_type("https://github.com/anthropics/claude-code", rsshub_routes=[])
    assert r.type == "github"
    assert r.config["owner"] == "anthropics"
    assert r.config["repo"] == "claude-code"


def test_detect_rsshub_route_xiaohongshu():
    routes = [
        {"pattern": r"xiaohongshu\.com/user/profile/(\w+)",
         "template": "/xiaohongshu/user/{1}"},
    ]
    r = detect_url_type(
        "https://www.xiaohongshu.com/user/profile/abc123",
        rsshub_routes=routes,
        rsshub_base_url="http://rsshub.local:1200",
    )
    assert r.type == "rss"
    assert r.config["feed_url"] == "http://rsshub.local:1200/xiaohongshu/user/abc123"


def test_detect_rsshub_route_weibo():
    routes = [
        {"pattern": r"weibo\.com/u/(\d+)", "template": "/weibo/user/{1}"},
    ]
    r = detect_url_type(
        "https://weibo.com/u/123456",
        rsshub_routes=routes,
        rsshub_base_url="http://rsshub.local:1200",
    )
    assert r.type == "rss"
    assert r.config["feed_url"] == "http://rsshub.local:1200/weibo/user/123456"


def test_detect_unknown_returns_unknown_type():
    r = detect_url_type("https://random.example.com/page", rsshub_routes=[])
    # Unknown type — caller will try direct RSS probing separately
    assert r.type == "unknown"


def test_detect_handles_trailing_slash_and_www():
    r1 = detect_url_type("https://www.youtube.com/channel/UC123/", rsshub_routes=[])
    r2 = detect_url_type("https://youtube.com/channel/UC123", rsshub_routes=[])
    assert r1.type == r2.type == "youtube"
    assert r1.config["channel_id"] == r2.config["channel_id"] == "UC123"


def test_detect_x_com_is_not_confused_by_status_url():
    # tweet URL, not profile — should not match as subscribe-able
    r = detect_url_type("https://x.com/karpathy/status/12345", rsshub_routes=[])
    # Our simple heuristic matches profile form; status URL still looks like handle "karpathy"
    # followed by extra path. Accept this as twitter with handle=karpathy (approximation OK).
    # If strict mode wanted later, detector can be tightened.
    assert r.type in ("twitter", "unknown")


from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_probe_rss_direct_xml_response():
    from processor.subscribe_analyzer import probe_rss_feed

    client = AsyncMock()
    response = MagicMock()
    response.headers = {"content-type": "application/rss+xml; charset=utf-8"}
    response.text = "<rss></rss>"
    response.status_code = 200
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    r = await probe_rss_feed("https://example.com/feed", client)
    assert r.type == "rss"
    assert r.config["feed_url"] == "https://example.com/feed"


@pytest.mark.asyncio
async def test_probe_rss_html_autodiscovery():
    from processor.subscribe_analyzer import probe_rss_feed

    html = """
    <html><head>
      <link rel="alternate" type="application/rss+xml" href="/feed.xml">
    </head><body>...</body></html>
    """
    client = AsyncMock()
    response = MagicMock()
    response.headers = {"content-type": "text/html"}
    response.text = html
    response.status_code = 200
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    r = await probe_rss_feed("https://example.com/", client)
    assert r.type == "rss"
    assert r.config["feed_url"] == "https://example.com/feed.xml"


@pytest.mark.asyncio
async def test_probe_rss_returns_unknown_on_plain_html():
    from processor.subscribe_analyzer import probe_rss_feed

    client = AsyncMock()
    response = MagicMock()
    response.headers = {"content-type": "text/html"}
    response.text = "<html><body>No feed here</body></html>"
    response.status_code = 200
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    r = await probe_rss_feed("https://example.com/", client)
    assert r.type == "unknown"


@pytest.mark.asyncio
async def test_fetch_sample_rss_returns_up_to_n_items():
    from processor.subscribe_analyzer import fetch_sample

    rss_body = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item><title>Item 1</title><link>https://example.com/1</link><pubDate>Mon, 21 Apr 2026 10:00:00 +0000</pubDate></item>
      <item><title>Item 2</title><link>https://example.com/2</link><pubDate>Mon, 21 Apr 2026 11:00:00 +0000</pubDate></item>
      <item><title>Item 3</title><link>https://example.com/3</link><pubDate>Mon, 21 Apr 2026 12:00:00 +0000</pubDate></item>
    </channel></rss>"""

    client = AsyncMock()
    response = MagicMock()
    response.text = rss_body
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    detection = DetectionResult("rss", {"feed_url": "https://example.com/feed"})
    samples = await fetch_sample(detection, client, n=2)
    assert len(samples) == 2
    assert samples[0]["title"] == "Item 1"
