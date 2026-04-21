"""Subscription analyzer: URL type detection + sample fetch + LLM judgment."""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    type: str                                  # 'rss' | 'youtube' | 'twitter' | 'bilibili' | 'reddit' | 'telegram' | 'github' | 'unknown'
    config: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None                # populated when type='unknown'


def detect_url_type(
    url: str,
    rsshub_routes: list[dict],
    rsshub_base_url: str = "",
) -> DetectionResult:
    """Run detector chain from most-specific to most-generic. First match wins.

    Covers all detectors determinable from URL pattern alone. Direct-RSS
    probing and HTML autodiscovery require HTTP — call probe_rss_feed(url)
    separately when detect_url_type returns 'unknown'.
    """
    # Strip fragment, normalize
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/")

    # 1) YouTube
    if host in ("youtube.com", "m.youtube.com"):
        m = re.match(r"^/channel/(UC[\w-]+)", path)
        if m:
            return DetectionResult("youtube", {"channel_id": m.group(1)})
        m = re.match(r"^/@([\w.-]+)", path)
        if m:
            return DetectionResult("youtube", {"handle": m.group(1)})

    # 2) Bilibili space
    if host == "space.bilibili.com":
        m = re.match(r"^/(\d+)", path)
        if m:
            return DetectionResult("bilibili", {"uid": m.group(1)})

    # 3) Twitter / X
    if host in ("twitter.com", "x.com"):
        m = re.match(r"^/([\w_]+)$", path) or re.match(r"^/([\w_]+)/status/", path)
        if m:
            return DetectionResult("twitter", {"handle": m.group(1)})

    # 4) Reddit subreddit
    if host == "reddit.com" or host.endswith(".reddit.com"):
        m = re.match(r"^/r/([\w_]+)", path)
        if m:
            return DetectionResult("reddit", {"subreddit": m.group(1)})

    # 5) Telegram
    if host == "t.me":
        m = re.match(r"^/([\w_]+)", path)
        if m:
            return DetectionResult("telegram", {"channel": m.group(1)})

    # 6) GitHub repo
    if host == "github.com":
        m = re.match(r"^/([\w.-]+)/([\w.-]+)", path)
        if m:
            return DetectionResult("github", {"owner": m.group(1), "repo": m.group(2)})

    # 7) RSSHub routes (full URL match including host)
    for route in rsshub_routes or []:
        pattern = route.get("pattern", "")
        template = route.get("template", "")
        if not pattern or not template:
            continue
        full_url = f"{parsed.hostname or ''}{parsed.path}"
        m = re.search(pattern, full_url)
        if m:
            feed_url = _fill_template(template, m)
            if rsshub_base_url:
                feed_url = rsshub_base_url.rstrip("/") + feed_url
            return DetectionResult("rss", {"feed_url": feed_url, "name": url})

    # 8) Fallback: unknown (caller may try probe_rss_feed next)
    return DetectionResult("unknown", error="No detector matched URL")


def _fill_template(template: str, match: re.Match) -> str:
    """Replace {1}, {2}, ... in template with match groups."""
    result = template
    for i, group in enumerate(match.groups(), start=1):
        result = result.replace(f"{{{i}}}", group)
    return result


async def probe_rss_feed(url: str, client: httpx.AsyncClient) -> DetectionResult:
    """HTTP-dependent fallback probe for RSS: try direct fetch + HTML autodiscovery."""
    try:
        response = await client.get(url, follow_redirects=True, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as e:
        return DetectionResult("unknown", error=f"HTTP error: {e}")
    except Exception as e:
        return DetectionResult("unknown", error=f"Fetch failed: {e}")

    ctype = (response.headers.get("content-type") or "").lower()
    body = response.text

    # Direct RSS: content-type indicates feed
    if any(t in ctype for t in ("application/rss", "application/atom", "text/xml", "application/xml")):
        return DetectionResult("rss", {"feed_url": url, "name": url})

    # Body starts with <rss or <feed — another direct hint
    stripped = body.lstrip()[:200].lower()
    if stripped.startswith(("<?xml", "<rss", "<feed")):
        return DetectionResult("rss", {"feed_url": url, "name": url})

    # HTML autodiscovery: look for <link rel="alternate" type="application/rss+xml" href="...">
    m = re.search(
        r'<link[^>]+rel=["\']alternate["\'][^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>',
        body, flags=re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]+rel=["\']alternate["\'][^>]*>',
            body, flags=re.IGNORECASE,
        )
    if m:
        link_tag = m.group(0)
        href_m = re.search(r'href=["\']([^"\']+)["\']', link_tag, flags=re.IGNORECASE)
        if href_m:
            feed_url = urljoin(url, href_m.group(1))
            return DetectionResult("rss", {"feed_url": feed_url, "name": url})

    return DetectionResult("unknown", error="No feed detected in page")
