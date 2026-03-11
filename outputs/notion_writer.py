"""Write news items to Notion database."""

import logging
from datetime import datetime

import httpx
from notion_client import AsyncClient

from collectors.base import ContentItem

logger = logging.getLogger(__name__)

SOURCE_LABEL = {
    "rss": "RSS",
    "youtube": "YouTube",
    "bilibili": "Bilibili",
    "twitter": "Twitter",
    "github": "GitHub",
    "hackernews": "HackerNews",
    "reddit": "Reddit",
    "telegram": "Telegram",
    "manual": "Manual",
}


class NotionWriter:
    def __init__(self, api_key: str, database_id: str, proxy: str | None = None):
        self.api_key = api_key
        self.database_id = database_id
        self.proxy = proxy
        client_kwargs: dict = {"auth": api_key}
        if proxy:
            client_kwargs["client"] = httpx.AsyncClient(proxy=proxy)
        self.client = AsyncClient(**client_kwargs)

    async def write_items(self, items: list[ContentItem]) -> int:
        """Write items to Notion database, skipping duplicates. Returns new count."""
        existing_urls = await self._get_existing_urls()
        logger.info("Notion: found %d existing entries", len(existing_urls))

        written = 0
        skipped = 0
        for item in items:
            if item.url.rstrip("/").lower() in existing_urls:
                skipped += 1
                continue
            try:
                await self._create_page(item)
                written += 1
            except Exception as e:
                logger.warning(
                    "Notion write failed for [%s]: %s", item.title[:50], e
                )
        logger.info(
            "Notion: wrote %d new, skipped %d duplicates (total %d)",
            written, skipped, len(items),
        )
        return written

    async def _get_existing_urls(self) -> set[str]:
        """Fetch all existing URLs from Notion database for dedup."""
        urls: set[str] = set()
        start_cursor: str | None = None
        api_url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        headers = self._api_headers()

        client_kwargs: dict = {"timeout": httpx.Timeout(30.0)}
        if self.proxy:
            client_kwargs["proxy"] = self.proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            while True:
                body: dict = {"page_size": 100}
                if start_cursor:
                    body["start_cursor"] = start_cursor

                resp = await client.post(api_url, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()

                for page in data["results"]:
                    url = page.get("properties", {}).get("URL", {}).get("url")
                    if url:
                        urls.add(url.rstrip("/").lower())

                if not data.get("has_more"):
                    break
                start_cursor = data.get("next_cursor")

        return urls

    async def backfill_ai_results(self, items: list[ContentItem]) -> int:
        """Update existing Notion pages with AI score/summary/categories.

        Matches by URL and only updates pages missing Importance.
        """
        url_to_item: dict[str, ContentItem] = {}
        for item in items:
            if item.ai_score is not None:
                url_to_item[item.url.rstrip("/").lower()] = item

        if not url_to_item:
            logger.info("Notion backfill: no items with AI scores")
            return 0

        # Fetch all pages from Notion with their URL and Importance
        page_map = await self._get_pages_needing_update()
        logger.info(
            "Notion backfill: %d pages need update, %d items have scores",
            len(page_map), len(url_to_item),
        )

        updated = 0
        for url_key, page_id in page_map.items():
            item = url_to_item.get(url_key)
            if not item:
                continue
            try:
                await self._update_page_ai(page_id, item)
                updated += 1
            except Exception as e:
                logger.warning("Notion backfill failed [%s]: %s", page_id[:8], e)

        logger.info("Notion backfill: updated %d pages", updated)
        return updated

    async def _get_pages_needing_update(self) -> dict[str, str]:
        """Fetch pages where Importance is empty. Returns {url: page_id}."""
        page_map: dict[str, str] = {}
        start_cursor: str | None = None
        api_url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        headers = self._api_headers()

        client_kwargs: dict = {"timeout": httpx.Timeout(30.0)}
        if self.proxy:
            client_kwargs["proxy"] = self.proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            while True:
                body: dict = {
                    "page_size": 100,
                    "filter": {
                        "property": "Importance",
                        "number": {"is_empty": True},
                    },
                }
                if start_cursor:
                    body["start_cursor"] = start_cursor

                resp = await client.post(api_url, headers=headers, json=body)
                resp.raise_for_status()
                data = resp.json()

                for page in data["results"]:
                    url = page.get("properties", {}).get("URL", {}).get("url")
                    if url:
                        page_map[url.rstrip("/").lower()] = page["id"]

                if not data.get("has_more"):
                    break
                start_cursor = data.get("next_cursor")

        return page_map

    async def _update_page_ai(self, page_id: str, item: ContentItem) -> None:
        """Update a Notion page with AI results."""
        properties: dict = {}
        if item.ai_score is not None:
            properties["Importance"] = {"number": item.ai_score}
        if item.ai_summary:
            properties["Summary"] = {
                "rich_text": [{"text": {"content": item.ai_summary[:2000]}}]
            }
        if item.ai_categories:
            properties["Category"] = {
                "multi_select": [{"name": c} for c in item.ai_categories[:5]]
            }
        if properties:
            await self.client.pages.update(page_id=page_id, properties=properties)

    def _api_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    async def _create_page(self, item: ContentItem) -> None:
        properties = {
            "Title": {"title": [{"text": {"content": item.title[:100]}}]},
            "Source": {"select": {"name": SOURCE_LABEL.get(
                item.source_type.value, item.source_type.value
            )}},
            "URL": {"url": item.url},
            "Author": {"rich_text": [{"text": {"content": item.author[:100]}}]},
        }

        if item.ai_categories:
            properties["Category"] = {
                "multi_select": [{"name": c} for c in item.ai_categories[:5]]
            }

        if item.ai_summary:
            properties["Summary"] = {
                "rich_text": [{"text": {"content": item.ai_summary[:2000]}}]
            }

        if item.ai_score is not None:
            properties["Importance"] = {"number": item.ai_score}

        if item.published_at:
            properties["Date"] = {
                "date": {"start": item.published_at.strftime("%Y-%m-%d")}
            }

        properties["Collected"] = {
            "date": {"start": item.collected_at.strftime("%Y-%m-%d")}
        }

        await self.client.pages.create(
            parent={"database_id": self.database_id},
            properties=properties,
        )
