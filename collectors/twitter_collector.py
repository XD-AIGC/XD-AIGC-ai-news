"""Twitter/X collector via Nitter RSS feeds."""

import calendar
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import md5

import feedparser
import httpx

from collectors.base import BaseScraper, ContentItem, SourceType, Theme

logger = logging.getLogger(__name__)

NITTER_INSTANCES = [
    "https://nitter.net",
]


class TwitterCollector(BaseScraper):
    """Collect tweets from X/Twitter users via Nitter RSS feeds."""

    def __init__(self, config: dict, http_client: httpx.AsyncClient):
        super().__init__(config, http_client)
        self.users = config.get("users", [])
        self.proxy = config.get("proxy", "")

    async def fetch(self, since: datetime) -> list[ContentItem]:
        items: list[ContentItem] = []
        client_kwargs: dict = {
            "timeout": httpx.Timeout(20.0),
            "follow_redirects": True,
        }
        if self.proxy:
            client_kwargs["proxy"] = self.proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            for user_cfg in self.users:
                screen_name = user_cfg["id"]
                name = user_cfg.get("name", screen_name)
                theme = Theme(user_cfg.get("theme", "ai"))
                try:
                    user_items = await self._fetch_nitter_rss(
                        client, screen_name, name, since, theme
                    )
                    items.extend(user_items)
                except Exception as e:
                    logger.warning("Twitter [%s] error: %s", name, e)

        return items

    async def _fetch_nitter_rss(
        self,
        client: httpx.AsyncClient,
        screen_name: str,
        name: str,
        since: datetime,
        theme: Theme = Theme("ai"),
    ) -> list[ContentItem]:
        """Fetch user tweets via Nitter RSS feed."""
        items: list[ContentItem] = []

        for base_url in NITTER_INSTANCES:
            rss_url = f"{base_url}/{screen_name}/rss"
            try:
                resp = await client.get(
                    rss_url,
                    headers={"User-Agent": "Mozilla/5.0 AI-News-Bot/1.0"},
                )
                resp.raise_for_status()
                feed = feedparser.parse(resp.text)

                if not feed.entries:
                    continue

                for entry in feed.entries:
                    item = self._parse_entry(entry, screen_name, name, since, theme)
                    if item:
                        items.append(item)

                logger.info("Twitter [%s]: fetched %d items", name, len(items))
                return items

            except httpx.HTTPError as e:
                logger.debug("Nitter [%s] %s failed: %s", name, base_url, e)
                continue

        logger.warning("Twitter [%s]: all Nitter instances failed", name)
        return items

    def _parse_entry(
        self,
        entry: dict,
        screen_name: str,
        name: str,
        since: datetime,
        theme: Theme = Theme("ai"),
    ) -> ContentItem | None:
        published_at = self._parse_date(entry)
        if published_at and published_at < since:
            return None

        title_raw = entry.get("title", "")
        content = entry.get("description", "") or entry.get("summary", "")

        title = title_raw[:120].replace("\n", " ")
        if len(title_raw) > 120:
            title += "..."

        link = entry.get("link", "")
        url = link.replace("nitter.net", "x.com") if link else ""

        if not title or not url:
            return None

        uid = md5(url.encode()).hexdigest()[:12]

        return ContentItem(
            id=self._generate_id("twitter", screen_name, uid),
            source_type=SourceType.TWITTER,
            title=title,
            url=url,
            content=content,
            author=name,
            published_at=published_at,
            theme=theme,
            metadata={"platform": "twitter"},
        )

    @staticmethod
    def _parse_date(entry: dict) -> datetime | None:
        for field in ("published", "updated"):
            if field not in entry:
                continue
            try:
                parsed_key = f"{field}_parsed"
                if parsed_key in entry and entry[parsed_key]:
                    return datetime.fromtimestamp(
                        calendar.timegm(entry[parsed_key]), tz=timezone.utc
                    )
                return parsedate_to_datetime(entry[field])
            except Exception:
                continue
        return None
