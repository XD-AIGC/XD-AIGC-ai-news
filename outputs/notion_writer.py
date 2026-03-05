"""Write news items to Notion database."""

import logging
from datetime import datetime

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
    def __init__(self, api_key: str, database_id: str):
        self.client = AsyncClient(auth=api_key)
        self.database_id = database_id

    async def write_items(self, items: list[ContentItem]) -> int:
        """Write items to Notion database. Returns count of items written."""
        written = 0
        for item in items:
            try:
                await self._create_page(item)
                written += 1
            except Exception as e:
                logger.warning(
                    "Notion write failed for [%s]: %s", item.title[:50], e
                )
        logger.info("Notion: wrote %d / %d items", written, len(items))
        return written

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
