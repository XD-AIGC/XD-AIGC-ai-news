"""Hacker News scraper via Firebase API."""

import asyncio
import logging
import re
from datetime import datetime, timezone

import httpx

from collectors.base import BaseScraper, ContentItem, SourceType

logger = logging.getLogger(__name__)

HN_API = "https://hacker-news.firebaseio.com/v0"
TOP_COMMENTS_LIMIT = 5


class HackerNewsCollector(BaseScraper):
    """Scraper for Hacker News top stories with comments."""

    async def fetch(self, since: datetime) -> list[ContentItem]:
        if not self.config.get("enabled", True):
            return []

        try:
            resp = await self.client.get(
                f"{HN_API}/topstories.json", timeout=30.0
            )
            resp.raise_for_status()
            story_ids = resp.json()

            fetch_count = self.config.get("fetch_top_stories", 30)
            story_ids = story_ids[:fetch_count]

            stories = await asyncio.gather(
                *[self._fetch_item(sid) for sid in story_ids],
                return_exceptions=True,
            )

            min_score = self.config.get("min_score", 100)
            valid_stories: list[dict] = []
            comment_tasks = []

            for story in stories:
                if isinstance(story, Exception) or story is None:
                    continue
                if story.get("score", 0) < min_score:
                    continue
                published_at = datetime.fromtimestamp(
                    story["time"], tz=timezone.utc
                )
                if published_at < since:
                    continue
                valid_stories.append(story)
                comment_ids = story.get("kids", [])[:TOP_COMMENTS_LIMIT]
                comment_tasks.append(self._fetch_comments(comment_ids))

            all_comments = await asyncio.gather(
                *comment_tasks, return_exceptions=True
            )

            items: list[ContentItem] = []
            for story, comments in zip(valid_stories, all_comments):
                if isinstance(comments, Exception):
                    comments = []
                item = self._parse_story(story, comments)
                if item:
                    items.append(item)

            logger.info("HackerNews: fetched %d stories", len(items))
            return items

        except httpx.HTTPError as e:
            logger.warning("HackerNews error: %s", e)
            return []

    async def _fetch_item(self, item_id: int) -> dict | None:
        try:
            resp = await self.client.get(
                f"{HN_API}/item/{item_id}.json", timeout=15.0
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError:
            return None

    async def _fetch_comments(self, comment_ids: list[int]) -> list[dict]:
        if not comment_ids:
            return []
        results = await asyncio.gather(
            *[self._fetch_item(cid) for cid in comment_ids],
            return_exceptions=True,
        )
        return [
            r
            for r in results
            if isinstance(r, dict)
            and r.get("text")
            and not r.get("deleted")
            and not r.get("dead")
        ]

    def _parse_story(
        self, story: dict, comments: list[dict]
    ) -> ContentItem | None:
        story_id = story["id"]
        title = story.get("title", "")
        url = story.get(
            "url", f"https://news.ycombinator.com/item?id={story_id}"
        )
        published_at = datetime.fromtimestamp(story["time"], tz=timezone.utc)

        parts: list[str] = []
        if story.get("text"):
            parts.append(story["text"])

        if comments:
            parts.append("\n--- Top Comments ---")
            for c in comments:
                commenter = c.get("by", "anon")
                text = re.sub(r"<[^>]+>", " ", c.get("text", "")).strip()
                if len(text) > 500:
                    text = text[:497] + "..."
                parts.append(f"[{commenter}]: {text}")

        hn_url = f"https://news.ycombinator.com/item?id={story_id}"

        return ContentItem(
            id=self._generate_id("hackernews", "story", str(story_id)),
            source_type=SourceType.HACKERNEWS,
            title=title,
            url=url,
            content="\n\n".join(parts),
            author=story.get("by", "unknown"),
            published_at=published_at,
            metadata={
                "score": story.get("score", 0),
                "comments_count": story.get("descendants", 0),
                "discussion_url": hn_url,
            },
        )
