"""Tests for image_url extraction in RSSCollector."""

import feedparser

from collectors.rss_collector import RSSCollector


def _entries(xml: str) -> list:
    return feedparser.parse(xml).entries


def test_extract_image_from_enclosure_image_type():
    xml = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
    <item><title>i</title><link>https://e.com/1</link>
    <enclosure url="https://e.com/cover.jpg" type="image/jpeg"/></item>
    </channel></rss>"""
    entry = _entries(xml)[0]
    assert RSSCollector._extract_image_url(entry) == "https://e.com/cover.jpg"


def test_extract_image_skips_non_image_enclosure():
    xml = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
    <item><title>i</title><link>https://e.com/1</link>
    <enclosure url="https://e.com/audio.mp3" type="audio/mpeg"/></item>
    </channel></rss>"""
    entry = _entries(xml)[0]
    assert RSSCollector._extract_image_url(entry) is None


def test_extract_image_from_media_thumbnail():
    xml = """<?xml version="1.0"?><rss version="2.0"
        xmlns:media="http://search.yahoo.com/mrss/"><channel><title>t</title>
    <item><title>i</title><link>https://e.com/2</link>
    <media:thumbnail url="https://e.com/thumb.jpg"/></item>
    </channel></rss>"""
    entry = _entries(xml)[0]
    assert RSSCollector._extract_image_url(entry) == "https://e.com/thumb.jpg"


def test_extract_image_from_media_content():
    xml = """<?xml version="1.0"?><rss version="2.0"
        xmlns:media="http://search.yahoo.com/mrss/"><channel><title>t</title>
    <item><title>i</title><link>https://e.com/3</link>
    <media:content url="https://e.com/media.jpg" type="image/jpeg"/></item>
    </channel></rss>"""
    entry = _entries(xml)[0]
    assert RSSCollector._extract_image_url(entry) == "https://e.com/media.jpg"


def test_extract_image_from_first_img_in_summary():
    xml = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
    <item><title>i</title><link>https://e.com/4</link>
    <description>&lt;p&gt;hi&lt;/p&gt;&lt;img src="https://e.com/inline.jpg"/&gt;</description>
    </item></channel></rss>"""
    entry = _entries(xml)[0]
    assert RSSCollector._extract_image_url(entry) == "https://e.com/inline.jpg"


def test_extract_image_returns_none_when_no_image():
    xml = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
    <item><title>i</title><link>https://e.com/5</link>
    <description>just text, nothing visual</description></item>
    </channel></rss>"""
    entry = _entries(xml)[0]
    assert RSSCollector._extract_image_url(entry) is None


def test_enclosure_takes_priority_over_inline_img():
    xml = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
    <item><title>i</title><link>https://e.com/6</link>
    <enclosure url="https://e.com/enc.jpg" type="image/jpeg"/>
    <description>&lt;img src="https://e.com/inline.jpg"/&gt;</description>
    </item></channel></rss>"""
    entry = _entries(xml)[0]
    assert RSSCollector._extract_image_url(entry) == "https://e.com/enc.jpg"
