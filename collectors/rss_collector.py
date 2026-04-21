"""RSS/Atom feed scraper. Also handles Bilibili/Twitter via RSSHub."""

import calendar
import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import md5

import feedparser
import httpx

from collectors.base import BaseScraper, ContentItem, SourceType, Theme

logger = logging.getLogger(__name__)


class RSSCollector(BaseScraper):
    """Scraper for RSS/Atom feeds."""

    def __init__(
        self,
        feeds: list[dict],
        http_client: httpx.AsyncClient,
        source_type: SourceType = SourceType.RSS,
    ):
        super().__init__({"feeds": feeds}, http_client)
        self.source_type = source_type

    async def fetch(self, since: datetime) -> list[ContentItem]:
        items: list[ContentItem] = []
        for feed_cfg in self.config["feeds"]:
            feed_items = await self._fetch_feed(feed_cfg, since)
            items.extend(feed_items)
        return items

    async def _fetch_feed(
        self, feed_cfg: dict, since: datetime
    ) -> list[ContentItem]:
        url = feed_cfg["url"]
        name = feed_cfg.get("name", url)
        theme = Theme(feed_cfg.get("theme", "ai"))
        items: list[ContentItem] = []

        try:
            response = await self.client.get(url, follow_redirects=True, timeout=30.0)
            response.raise_for_status()
            feed = feedparser.parse(response.text)

            for entry in feed.entries:
                published_at = self._parse_date(entry)
                if published_at and published_at < since:
                    continue

                entry_id = entry.get("id", entry.get("link", ""))
                uid = md5(entry_id.encode()).hexdigest()[:12]

                item = ContentItem(
                    id=self._generate_id(
                        self.source_type.value, name.replace(" ", "_"), uid
                    ),
                    source_type=self.source_type,
                    title=entry.get("title", "Untitled"),
                    url=entry.get("link", url),
                    content=self._extract_content(entry),
                    author=entry.get("author", name),
                    published_at=published_at,
                    theme=theme,
                    metadata={
                        "feed_name": name,
                        "tags": [t.term for t in entry.get("tags", [])],
                    },
                )
                items.append(item)

            logger.info("RSS [%s]: fetched %d items", name, len(items))

        except httpx.HTTPError as e:
            logger.warning("RSS [%s] HTTP error: %s", name, e)
        except Exception as e:
            logger.warning("RSS [%s] parse error: %s", name, e)

        return items

    @staticmethod
    def _parse_date(entry: dict) -> datetime | None:
        for field in ("published", "updated", "created"):
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

    @staticmethod
    def _extract_content(entry: dict) -> str:
        if "summary" in entry:
            return entry.summary
        if "description" in entry:
            return entry.description
        if "content" in entry and entry.content:
            return entry.content[0].get("value", "")
        return ""
