"""YouTube Data API v3 scraper: channel videos + keyword search by view count."""

import logging
import os
from datetime import datetime, timezone
from hashlib import md5

import httpx

from collectors.base import BaseScraper, ContentItem, SourceType, Theme

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeCollector(BaseScraper):
    """Scraper for YouTube channels + trending AI video search."""

    def __init__(self, config: dict, http_client: httpx.AsyncClient):
        super().__init__(config, http_client)
        self.api_key = config.get("api_key") or os.getenv("YOUTUBE_API_KEY", "")

    async def fetch(self, since: datetime) -> list[ContentItem]:
        if not self.api_key:
            logger.warning("YouTube: no API key configured, skipping")
            return []

        items: list[ContentItem] = []

        # 1. Channel subscriptions
        for ch in self.config.get("channels", []):
            ch_items = await self._fetch_channel(ch, since)
            items.extend(ch_items)

        # 2. Keyword search for trending AI videos
        search_cfg = self.config.get("search", {})
        if search_cfg.get("enabled"):
            search_items = await self._search_trending(search_cfg, since)
            items.extend(search_items)

        return items

    async def _fetch_channel(
        self, channel_cfg: dict, since: datetime
    ) -> list[ContentItem]:
        channel_id = channel_cfg["id"]
        channel_name = channel_cfg.get("name", channel_id)
        theme = Theme(channel_cfg.get("theme", "ai"))
        items: list[ContentItem] = []

        try:
            params = {
                "key": self.api_key,
                "channelId": channel_id,
                "part": "snippet",
                "order": "date",
                "type": "video",
                "publishedAfter": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "maxResults": 10,
            }

            resp = await self.client.get(
                f"{YOUTUBE_API_BASE}/search",
                params=params,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()

            for entry in data.get("items", []):
                item = self._parse_search_item(entry, channel_name, theme=theme)
                if item:
                    items.append(item)

            logger.info(
                "YouTube [%s]: fetched %d videos", channel_name, len(items)
            )

        except httpx.HTTPError as e:
            logger.warning("YouTube [%s] error: %s", channel_name, e)
        except Exception as e:
            logger.warning("YouTube [%s] parse error: %s", channel_name, e)

        return items

    async def _search_trending(
        self, cfg: dict, since: datetime
    ) -> list[ContentItem]:
        """Search YouTube for trending AI videos by keyword, sorted by view count."""
        queries = cfg.get("queries", [])
        top_n = cfg.get("top_n", 10)

        all_items: list[ContentItem] = []
        seen_ids: set[str] = set()

        for query in queries:
            try:
                params = {
                    "key": self.api_key,
                    "q": query,
                    "part": "snippet",
                    "order": "viewCount",
                    "type": "video",
                    "publishedAfter": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "maxResults": 10,
                    "relevanceLanguage": "en",
                }

                resp = await self.client.get(
                    f"{YOUTUBE_API_BASE}/search",
                    params=params,
                    timeout=30.0,
                )
                resp.raise_for_status()
                data = resp.json()

                for entry in data.get("items", []):
                    video_id = entry.get("id", {}).get("videoId", "")
                    if not video_id or video_id in seen_ids:
                        continue
                    seen_ids.add(video_id)

                    item = self._parse_search_item(entry, source_tag="search")
                    if item:
                        item.metadata["search_query"] = query
                        all_items.append(item)

            except httpx.HTTPError as e:
                logger.warning("YouTube search [%s] error: %s", query, e)
            except Exception as e:
                logger.warning("YouTube search [%s] parse error: %s", query, e)

        # Get view counts for all found videos to sort properly
        if all_items:
            all_items = await self._enrich_view_counts(all_items)
            all_items.sort(
                key=lambda x: x.metadata.get("view_count", 0), reverse=True
            )

        top = all_items[:top_n]
        logger.info(
            "YouTube search: %d candidates -> top %d by views",
            len(all_items), len(top),
        )
        return top

    async def _enrich_view_counts(
        self, items: list[ContentItem]
    ) -> list[ContentItem]:
        """Fetch actual view counts via videos.list API for sorting."""
        video_ids = [
            item.metadata.get("video_id", "") for item in items
            if item.metadata.get("video_id")
        ]
        if not video_ids:
            return items

        # Batch in groups of 50 (API limit)
        view_map: dict[str, int] = {}
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            try:
                resp = await self.client.get(
                    f"{YOUTUBE_API_BASE}/videos",
                    params={
                        "key": self.api_key,
                        "id": ",".join(batch),
                        "part": "statistics",
                    },
                    timeout=30.0,
                )
                resp.raise_for_status()
                data = resp.json()
                for v in data.get("items", []):
                    vid = v["id"]
                    stats = v.get("statistics", {})
                    view_map[vid] = int(stats.get("viewCount", 0))
            except Exception as e:
                logger.warning("YouTube view count batch error: %s", e)

        for item in items:
            vid = item.metadata.get("video_id", "")
            if vid in view_map:
                views = view_map[vid]
                item.metadata["view_count"] = views
                # Prepend view count to title for visibility
                if views >= 1000:
                    views_str = (
                        f"{views / 1_000_000:.1f}M" if views >= 1_000_000
                        else f"{views / 1_000:.0f}K"
                    )
                    item.title = f"[{views_str} views] {item.title}"

        return items

    def _parse_search_item(
        self, entry: dict, source_tag: str = "", theme: Theme = Theme("ai")
    ) -> ContentItem | None:
        """Parse a YouTube search API result item."""
        snippet = entry.get("snippet", {})
        video_id = entry.get("id", {}).get("videoId", "")
        if not video_id:
            return None

        published_at = self._parse_datetime(snippet.get("publishedAt", ""))
        channel_name = snippet.get("channelTitle", source_tag)

        return ContentItem(
            id=self._generate_id("youtube", source_tag or "channel", video_id),
            source_type=SourceType.YOUTUBE,
            title=snippet.get("title", ""),
            url=f"https://www.youtube.com/watch?v={video_id}",
            content=snippet.get("description", ""),
            author=channel_name,
            published_at=published_at,
            theme=theme,
            metadata={
                "channel_id": snippet.get("channelId", ""),
                "channel_name": channel_name,
                "video_id": video_id,
                "thumbnail": snippet.get("thumbnails", {})
                .get("high", {})
                .get("url", ""),
            },
        )

    @staticmethod
    def _parse_datetime(dt_str: str) -> datetime | None:
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except ValueError:
            return None
