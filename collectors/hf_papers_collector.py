"""Hugging Face Daily Papers collector via API."""

import logging
from datetime import datetime, timezone

from collectors.base import BaseScraper, ContentItem, SourceType

logger = logging.getLogger(__name__)

HF_PAPERS_API = "https://huggingface.co/api/daily_papers"


class HFPapersCollector(BaseScraper):
    """Fetch trending papers from Hugging Face Daily Papers."""

    async def fetch(self, since: datetime) -> list[ContentItem]:
        min_upvotes = self.config.get("min_upvotes", 0)
        limit = self.config.get("limit", 50)

        try:
            resp = await self.client.get(
                HF_PAPERS_API,
                params={"limit": limit},
                timeout=30.0,
            )
            resp.raise_for_status()
            papers = resp.json()
        except Exception as e:
            logger.warning("HF Papers API error: %s", e)
            return []

        items: list[ContentItem] = []
        for entry in papers:
            paper = entry.get("paper", {})
            paper_id = paper.get("id", "")

            published_str = entry.get("publishedAt", "")
            published_at = self._parse_time(published_str)
            if published_at and published_at < since:
                continue

            upvotes = paper.get("upvotes", 0) or 0
            if upvotes < min_upvotes:
                continue

            title = entry.get("title") or paper.get("title", "Untitled")
            summary = paper.get("summary", "") or ""
            ai_summary = paper.get("ai_summary") or ""
            ai_keywords = paper.get("ai_keywords") or []
            authors = [a.get("name", "") for a in paper.get("authors", [])]

            item = ContentItem(
                id=self._generate_id("hf_papers", "daily", paper_id),
                source_type=SourceType.HF_PAPERS,
                title=title,
                url=f"https://huggingface.co/papers/{paper_id}",
                content=ai_summary if ai_summary else summary[:1000],
                author=", ".join(authors[:3]),
                published_at=published_at,
                metadata={
                    "arxiv_id": paper_id,
                    "upvotes": upvotes,
                    "ai_keywords": ai_keywords,
                    "num_comments": entry.get("numComments", 0),
                    "submitted_by": (entry.get("submittedBy") or {}).get("name", ""),
                },
            )
            items.append(item)

        logger.info("HF Papers: fetched %d items (min_upvotes=%d)", len(items), min_upvotes)
        return items

    @staticmethod
    def _parse_time(time_str: str) -> datetime | None:
        if not time_str:
            return None
        try:
            return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
