"""Reddit scraper via public JSON API."""

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from collectors.base import BaseScraper, ContentItem, SourceType

logger = logging.getLogger(__name__)

REDDIT_BASE = "https://www.reddit.com"
USER_AGENT = "XD-AIGC-News/1.0 (AI news aggregator)"


class RedditCollector(BaseScraper):
    """Scraper for Reddit subreddits via public JSON API."""

    async def fetch(self, since: datetime) -> list[ContentItem]:
        if not self.config.get("enabled", True):
            return []

        tasks = []
        for sub_cfg in self.config.get("subreddits", []):
            tasks.append(self._fetch_subreddit(sub_cfg, since))

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        items: list[ContentItem] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Reddit fetch error: %s", result)
            elif isinstance(result, list):
                items.extend(result)
        return items

    async def _fetch_subreddit(
        self, cfg: dict, since: datetime
    ) -> list[ContentItem]:
        subreddit = cfg["name"]
        sort = cfg.get("sort", "hot")
        min_score = cfg.get("min_score", 10)
        fetch_limit = cfg.get("fetch_limit", 25)
        fetch_comments = self.config.get("fetch_comments", 5)

        url = f"{REDDIT_BASE}/r/{subreddit}/{sort}.json"
        params = {"limit": min(fetch_limit, 100), "raw_json": 1}
        if sort in ("top", "controversial"):
            params["t"] = cfg.get("time_filter", "day")

        data = await self._reddit_get(url, params)
        if not data:
            return []

        posts = [
            child["data"]
            for child in data.get("data", {}).get("children", [])
            if child.get("kind") == "t3"
        ]

        valid_posts: list[dict] = []
        comment_tasks = []

        for post in posts:
            created = datetime.fromtimestamp(
                post.get("created_utc", 0), tz=timezone.utc
            )
            if created < since:
                continue
            if post.get("score", 0) < min_score:
                continue
            valid_posts.append(post)
            if fetch_comments > 0:
                comment_tasks.append(
                    self._fetch_comments(subreddit, post["id"], fetch_comments)
                )
            else:
                comment_tasks.append(asyncio.coroutine(lambda: [])())

        if not valid_posts:
            return []

        all_comments = await asyncio.gather(
            *comment_tasks, return_exceptions=True
        )

        items: list[ContentItem] = []
        for post, comments in zip(valid_posts, all_comments):
            if isinstance(comments, Exception):
                comments = []
            item = self._parse_post(post, comments)
            if item:
                items.append(item)

        logger.info("Reddit [r/%s]: fetched %d posts", subreddit, len(items))
        return items

    async def _fetch_comments(
        self, subreddit: str, post_id: str, limit: int
    ) -> list[dict]:
        url = f"{REDDIT_BASE}/r/{subreddit}/comments/{post_id}.json"
        params = {"limit": limit, "depth": 1, "sort": "top", "raw_json": 1}

        data = await self._reddit_get(url, params)
        if not data or not isinstance(data, list) or len(data) < 2:
            return []

        comments = []
        for child in data[1].get("data", {}).get("children", []):
            if child.get("kind") != "t1":
                continue
            c = child["data"]
            if c.get("body") and c.get("distinguished") != "moderator":
                comments.append(c)

        comments.sort(key=lambda c: c.get("score", 0), reverse=True)
        return comments[:limit]

    def _parse_post(
        self, post: dict, comments: list[dict]
    ) -> ContentItem | None:
        post_id = post["id"]
        title = post.get("title", "")
        subreddit = post.get("subreddit", "")
        permalink = post.get("permalink", "")
        discussion_url = f"https://www.reddit.com{permalink}"
        is_self = post.get("is_self", False)
        url = discussion_url if is_self else post.get("url", discussion_url)
        created = datetime.fromtimestamp(
            post.get("created_utc", 0), tz=timezone.utc
        )

        parts: list[str] = []
        if post.get("selftext"):
            text = post["selftext"]
            if len(text) > 1500:
                text = text[:1497] + "..."
            parts.append(text)

        if comments:
            parts.append("\n--- Top Comments ---")
            for c in comments:
                author = c.get("author", "anon")
                body = c.get("body", "").strip()
                if len(body) > 500:
                    body = body[:497] + "..."
                score = c.get("score", 0)
                parts.append(f"[{author} ({score} pts)]: {body}")

        return ContentItem(
            id=self._generate_id("reddit", subreddit, post_id),
            source_type=SourceType.REDDIT,
            title=title,
            url=url,
            content="\n\n".join(parts),
            author=post.get("author", "unknown"),
            published_at=created,
            metadata={
                "score": post.get("score", 0),
                "upvote_ratio": post.get("upvote_ratio"),
                "num_comments": post.get("num_comments", 0),
                "subreddit": subreddit,
                "flair": post.get("link_flair_text"),
                "discussion_url": discussion_url,
            },
        )

    async def _reddit_get(self, url: str, params: dict) -> dict | list | None:
        headers = {"User-Agent": USER_AGENT}
        try:
            resp = await self.client.get(
                url,
                params=params,
                headers=headers,
                follow_redirects=True,
                timeout=30.0,
            )
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 5))
                logger.warning(
                    "Reddit rate limited, retrying after %ds", retry_after
                )
                await asyncio.sleep(retry_after)
                resp = await self.client.get(
                    url,
                    params=params,
                    headers=headers,
                    follow_redirects=True,
                    timeout=30.0,
                )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.warning("Reddit request failed for %s: %s", url, e)
            return None
