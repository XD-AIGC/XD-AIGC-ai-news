"""Twitter trending AI content collector via twikit (free, no API key).

Searches for AI-related tweets across all of Twitter, ranked by
engagement (likes), and returns the top N results — not tied to
any fixed set of accounts.
"""

import logging
import os
from datetime import datetime, timezone
from hashlib import md5
from pathlib import Path

import httpx

from collectors.base import BaseScraper, ContentItem, SourceType

logger = logging.getLogger(__name__)

COOKIES_PATH = Path("data/twitter_cookies.json")


class TwitterTrendingCollector(BaseScraper):
    """Collect top-liked AI tweets via twikit search."""

    def __init__(self, config: dict, http_client: httpx.AsyncClient):
        super().__init__(config, http_client)
        self.queries = config.get("search_queries", [])
        self.min_likes = config.get("min_likes", 500)
        self.top_n = config.get("top_n", 10)
        self.proxy = config.get("proxy", "")
        self.auth_token = config.get("auth_token", "") or os.getenv(
            "TWITTER_AUTH_TOKEN", ""
        )

    async def fetch(self, since: datetime) -> list[ContentItem]:
        if not self.auth_token and not COOKIES_PATH.exists():
            logger.warning(
                "TwitterTrending: no auth_token or cookies file, skipping"
            )
            return []

        try:
            from twikit import Client
        except ImportError:
            logger.error(
                "TwitterTrending: twikit not installed (pip install twikit)"
            )
            return []

        client = Client("en-US", proxy=self.proxy if self.proxy else None)

        # Authenticate: try saved cookies first, fallback to auth_token
        authenticated = False
        if COOKIES_PATH.exists():
            try:
                client.load_cookies(str(COOKIES_PATH))
                logger.debug("TwitterTrending: loaded saved cookies")
                authenticated = True
            except Exception as e:
                logger.warning("TwitterTrending: failed to load cookies: %s", e)

        if not authenticated and self.auth_token:
            ct0 = await self._fetch_ct0()
            if ct0:
                client.set_cookies({
                    "auth_token": self.auth_token,
                    "ct0": ct0,
                })
                # Save for next run
                COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
                try:
                    client.save_cookies(str(COOKIES_PATH))
                except Exception:
                    pass
                logger.info("TwitterTrending: authenticated with auth_token + ct0")
                authenticated = True
            else:
                logger.error("TwitterTrending: failed to get ct0 token")
                return []

        if not authenticated:
            logger.error("TwitterTrending: no valid authentication")
            return []

        all_items: list[ContentItem] = []

        for query in self.queries:
            try:
                items = await self._search_query(client, query, since)
                all_items.extend(items)
            except Exception as e:
                logger.warning(
                    "TwitterTrending search [%s] error: %s", query, e
                )

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
            "TwitterTrending: %d total -> %d unique -> top %d (min likes: %d)",
            len(all_items),
            len(unique),
            len(top),
            self.min_likes,
        )

        # Update saved cookies
        try:
            client.save_cookies(str(COOKIES_PATH))
        except Exception:
            pass

        return top

    async def _fetch_ct0(self) -> str:
        """Fetch ct0 CSRF token from Twitter using auth_token cookie."""
        try:
            client_kwargs: dict = {"timeout": httpx.Timeout(15.0)}
            if self.proxy:
                client_kwargs["proxy"] = self.proxy

            async with httpx.AsyncClient(**client_kwargs) as hc:
                resp = await hc.get(
                    "https://x.com",
                    cookies={"auth_token": self.auth_token},
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/131.0.0.0 Safari/537.36"
                        ),
                    },
                    follow_redirects=True,
                )
                ct0 = resp.cookies.get("ct0", "")
                if ct0:
                    logger.debug("TwitterTrending: fetched ct0 token")
                    return ct0

                # Try from Set-Cookie header
                for cookie in resp.headers.get_list("set-cookie"):
                    if "ct0=" in cookie:
                        ct0 = cookie.split("ct0=")[1].split(";")[0]
                        if ct0:
                            return ct0

        except Exception as e:
            logger.warning("TwitterTrending: ct0 fetch error: %s", e)

        return ""

    async def _search_query(
        self, client, query: str, since: datetime
    ) -> list[ContentItem]:
        """Search Twitter for a query, return items with min_likes filter."""
        items: list[ContentItem] = []

        # Use min_faves in query for server-side filtering
        search_q = f"{query} min_faves:{self.min_likes}"

        try:
            tweets = await client.search_tweet(search_q, "Top", count=20)

            for tweet in tweets:
                item = self._parse_tweet(tweet, since)
                if item:
                    items.append(item)

            logger.info(
                "TwitterTrending [%s]: fetched %d items", query, len(items)
            )

        except Exception as e:
            logger.warning("TwitterTrending [%s] search error: %s", query, e)

        return items

    def _parse_tweet(self, tweet, since: datetime) -> ContentItem | None:
        """Parse a twikit Tweet object into ContentItem."""
        # Check date
        published_at = None
        if tweet.created_at_datetime:
            published_at = tweet.created_at_datetime
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)
            if published_at < since:
                return None

        likes = tweet.favorite_count or 0
        retweets = tweet.retweet_count or 0
        replies = tweet.reply_count or 0
        views = tweet.view_count or 0

        if likes < self.min_likes:
            return None

        # Build content
        text = tweet.full_text or tweet.text or ""
        author_name = ""
        author_handle = ""
        if tweet.user:
            author_name = tweet.user.name or ""
            author_handle = tweet.user.screen_name or ""

        title = text[:120].replace("\n", " ")
        if len(text) > 120:
            title += "..."

        if not title:
            return None

        tweet_url = f"https://x.com/{author_handle}/status/{tweet.id}"
        uid = md5(tweet_url.encode()).hexdigest()[:12]

        return ContentItem(
            id=self._generate_id("twitter", "trending", uid),
            source_type=SourceType.TWITTER,
            title=title,
            url=tweet_url,
            content=text,
            author=(
                f"{author_name} (@{author_handle})"
                if author_handle
                else author_name
            ),
            published_at=published_at,
            metadata={
                "platform": "twitter",
                "trending": True,
                "likes": likes,
                "retweets": retweets,
                "replies": replies,
                "views": views,
            },
        )
