"""Twitter trending AI content collector via Nitter search.

Searches for AI-related tweets across all of Twitter, ranked by
engagement (likes), and returns the top N results — not tied to
any fixed set of accounts.
"""

import logging
import re
from datetime import datetime, timezone
from hashlib import md5
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from collectors.base import BaseScraper, ContentItem, SourceType

logger = logging.getLogger(__name__)

NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://xcancel.com",
    "https://nitter.privacyredirect.com",
    "https://nitter.net",
]

# Default search queries covering the project's focus areas
DEFAULT_QUERIES = [
    "AI breakthrough",
    "LLM open source",
    "Stable Diffusion OR Flux OR ComfyUI",
    "GPT OR Claude OR Gemini AI",
    "AI agent framework",
]


class TwitterTrendingCollector(BaseScraper):
    """Collect top-liked AI tweets from Twitter search results."""

    def __init__(self, config: dict, http_client: httpx.AsyncClient):
        super().__init__(config, http_client)
        self.queries = config.get("search_queries", DEFAULT_QUERIES)
        self.min_likes = config.get("min_likes", 500)
        self.top_n = config.get("top_n", 10)
        self.proxy = config.get("proxy", "")

    async def fetch(self, since: datetime) -> list[ContentItem]:
        all_items: list[ContentItem] = []

        client_kwargs: dict = {
            "timeout": httpx.Timeout(25.0),
            "follow_redirects": True,
        }
        if self.proxy:
            client_kwargs["proxy"] = self.proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            for query in self.queries:
                try:
                    items = await self._search_nitter(client, query, since)
                    all_items.extend(items)
                except Exception as e:
                    logger.warning("Twitter trending search [%s] error: %s", query, e)

        # Deduplicate by URL
        seen_urls: set[str] = set()
        unique: list[ContentItem] = []
        for item in all_items:
            if item.url not in seen_urls:
                seen_urls.add(item.url)
                unique.append(item)

        # Sort by likes descending, take top N
        unique.sort(
            key=lambda x: x.metadata.get("likes", 0), reverse=True
        )
        top = unique[: self.top_n]

        logger.info(
            "Twitter trending: %d total -> %d unique -> top %d (min likes: %d)",
            len(all_items), len(unique), len(top), self.min_likes,
        )
        return top

    async def _search_nitter(
        self, client: httpx.AsyncClient, query: str, since: datetime
    ) -> list[ContentItem]:
        """Search Nitter for tweets matching query, parse engagement metrics."""
        items: list[ContentItem] = []

        for base_url in NITTER_INSTANCES:
            search_url = f"{base_url}/search?f=tweets&q={quote_plus(query)}"
            try:
                resp = await client.get(
                    search_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml",
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                )
                resp.raise_for_status()

                parsed = self._parse_search_html(resp.text, base_url, since)
                if parsed:
                    items.extend(parsed)
                    logger.debug(
                        "Twitter trending [%s] via %s: %d items",
                        query, base_url, len(parsed),
                    )
                    return items

            except httpx.HTTPError as e:
                logger.debug("Nitter search [%s] %s failed: %s", query, base_url, e)
                continue

        logger.warning("Twitter trending [%s]: all Nitter instances failed", query)
        return items

    def _parse_search_html(
        self, html: str, base_url: str, since: datetime
    ) -> list[ContentItem]:
        """Parse Nitter search result HTML to extract tweets with metrics."""
        soup = BeautifulSoup(html, "html.parser")
        items: list[ContentItem] = []

        # Nitter wraps each tweet in a .timeline-item div
        tweet_cards = soup.select(".timeline-item")
        if not tweet_cards:
            # Try alternative selector
            tweet_cards = soup.select(".tweet-body")

        for card in tweet_cards:
            try:
                item = self._parse_tweet_card(card, base_url, since)
                if item:
                    items.append(item)
            except Exception as e:
                logger.debug("Failed to parse tweet card: %s", e)
                continue

        return items

    def _parse_tweet_card(
        self, card, base_url: str, since: datetime
    ) -> ContentItem | None:
        """Parse a single tweet card from Nitter HTML."""
        # Extract author
        author_el = card.select_one(".username")
        author = author_el.get_text(strip=True) if author_el else ""
        fullname_el = card.select_one(".fullname")
        fullname = fullname_el.get_text(strip=True) if fullname_el else author

        # Extract tweet link
        link_el = card.select_one(".tweet-link")
        if not link_el:
            link_el = card.select_one("a.tweet-link")
        if not link_el:
            # Try finding any link that looks like a tweet permalink
            for a in card.select("a"):
                href = a.get("href", "")
                if "/status/" in href:
                    link_el = a
                    break

        if not link_el:
            return None

        href = link_el.get("href", "")
        # Convert Nitter URL to x.com URL
        if href.startswith("/"):
            tweet_url = f"https://x.com{href}"
        else:
            tweet_url = href
            for instance in NITTER_INSTANCES:
                domain = instance.replace("https://", "").replace("http://", "")
                tweet_url = tweet_url.replace(domain, "x.com")

        tweet_url = tweet_url.split("#")[0]  # Remove fragment

        # Extract tweet content
        content_el = card.select_one(".tweet-content, .media-body")
        content = content_el.get_text(strip=True) if content_el else ""

        # Extract timestamp
        time_el = card.select_one("time")
        published_at = None
        if time_el:
            dt_str = time_el.get("datetime", "")
            if dt_str:
                try:
                    published_at = datetime.fromisoformat(
                        dt_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

        if published_at and published_at < since:
            return None

        # Extract engagement metrics
        likes = self._extract_stat(card, "icon-heart", "like")
        retweets = self._extract_stat(card, "icon-retweet", "retweet")
        replies = self._extract_stat(card, "icon-comment", "reply")

        # Filter by minimum likes
        if likes < self.min_likes:
            return None

        title = content[:120].replace("\n", " ")
        if len(content) > 120:
            title += "..."

        if not title:
            return None

        uid = md5(tweet_url.encode()).hexdigest()[:12]

        return ContentItem(
            id=self._generate_id("twitter", "trending", uid),
            source_type=SourceType.TWITTER,
            title=title,
            url=tweet_url,
            content=content,
            author=f"{fullname} ({author})" if author else fullname,
            published_at=published_at,
            metadata={
                "platform": "twitter",
                "trending": True,
                "likes": likes,
                "retweets": retweets,
                "replies": replies,
            },
        )

    @staticmethod
    def _extract_stat(card, icon_class: str, stat_name: str) -> int:
        """Extract a numeric stat (likes, retweets, replies) from a tweet card."""
        # Method 1: look for icon class + sibling text
        icon = card.select_one(f".{icon_class}")
        if icon:
            parent = icon.parent
            if parent:
                text = parent.get_text(strip=True)
                return _parse_count(text)

        # Method 2: look for .tweet-stat elements
        for stat_el in card.select(".tweet-stat"):
            text = stat_el.get_text(strip=True).lower()
            if stat_name in text or icon_class.replace("icon-", "") in text:
                return _parse_count(text)

        # Method 3: data attribute
        for attr_name in (f"data-{stat_name}s", f"data-{stat_name}-count"):
            el = card.select_one(f"[{attr_name}]")
            if el:
                try:
                    return int(el[attr_name])
                except (ValueError, KeyError):
                    pass

        return 0


def _parse_count(text: str) -> int:
    """Parse human-readable count like '1.2K' or '15,432' to int."""
    text = re.sub(r"[^\d.kKmM]", "", text)
    if not text:
        return 0

    text = text.strip()
    multiplier = 1
    if text[-1] in ("k", "K"):
        multiplier = 1000
        text = text[:-1]
    elif text[-1] in ("m", "M"):
        multiplier = 1_000_000
        text = text[:-1]

    try:
        return int(float(text) * multiplier)
    except ValueError:
        return 0
