"""YouTube Data API v3 scraper."""

import logging
import os
from datetime import datetime, timezone

import httpx

from collectors.base import BaseScraper, ContentItem, SourceType

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeCollector(BaseScraper):
    """Scraper for YouTube channels via Data API v3."""

    def __init__(self, config: dict, http_client: httpx.AsyncClient):
        super().__init__(config, http_client)
        self.api_key = config.get("api_key") or os.getenv("YOUTUBE_API_KEY", "")

    async def fetch(self, since: datetime) -> list[ContentItem]:
        if not self.api_key:
            logger.warning("YouTube: no API key configured, skipping")
            return []

        items: list[ContentItem] = []
        for ch in self.config.get("channels", []):
            ch_items = await self._fetch_channel(ch, since)
            items.extend(ch_items)
        return items

    async def _fetch_channel(
        self, channel_cfg: dict, since: datetime
    ) -> list[ContentItem]:
        channel_id = channel_cfg["id"]
        channel_name = channel_cfg.get("name", channel_id)
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
                snippet = entry.get("snippet", {})
                video_id = entry.get("id", {}).get("videoId", "")
                if not video_id:
                    continue

                published_at = self._parse_datetime(
                    snippet.get("publishedAt", "")
                )

                item = ContentItem(
                    id=self._generate_id("youtube", channel_id, video_id),
                    source_type=SourceType.YOUTUBE,
                    title=snippet.get("title", ""),
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    content=snippet.get("description", ""),
                    author=snippet.get("channelTitle", channel_name),
                    published_at=published_at,
                    metadata={
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                        "video_id": video_id,
                        "thumbnail": snippet.get("thumbnails", {})
                        .get("high", {})
                        .get("url", ""),
                    },
                )
                items.append(item)

            logger.info(
                "YouTube [%s]: fetched %d videos", channel_name, len(items)
            )

        except httpx.HTTPError as e:
            logger.warning("YouTube [%s] error: %s", channel_name, e)
        except Exception as e:
            logger.warning("YouTube [%s] parse error: %s", channel_name, e)

        return items

    @staticmethod
    def _parse_datetime(dt_str: str) -> datetime | None:
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        except ValueError:
            return None
