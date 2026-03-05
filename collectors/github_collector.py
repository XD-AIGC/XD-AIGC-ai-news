"""GitHub scraper: Trending via RSS + repo releases via REST API."""

import logging
import os
from datetime import datetime, timezone
from hashlib import md5

import feedparser
import httpx

from collectors.base import BaseScraper, ContentItem, SourceType

logger = logging.getLogger(__name__)


class GitHubCollector(BaseScraper):
    """Scraper for GitHub Trending (RSS) and watched repo releases (API)."""

    def __init__(self, config: dict, http_client: httpx.AsyncClient):
        super().__init__(config, http_client)
        self.token = os.getenv("GITHUB_TOKEN")
        self.api_base = "https://api.github.com"

    async def fetch(self, since: datetime) -> list[ContentItem]:
        items: list[ContentItem] = []

        trending_url = self.config.get("trending_rss")
        if trending_url:
            items.extend(await self._fetch_trending(trending_url, since))

        for repo_cfg in self.config.get("watch_repos", []):
            items.extend(
                await self._fetch_releases(
                    repo_cfg["owner"], repo_cfg["repo"], since
                )
            )

        return items

    async def _fetch_trending(
        self, rss_url: str, since: datetime
    ) -> list[ContentItem]:
        items: list[ContentItem] = []
        try:
            response = await self.client.get(
                rss_url, follow_redirects=True, timeout=30.0
            )
            response.raise_for_status()
            feed = feedparser.parse(response.text)

            for entry in feed.entries:
                link = entry.get("link", "")
                uid = md5(link.encode()).hexdigest()[:12]

                repo_name = link.replace("https://github.com/", "")
                description = entry.get("summary", entry.get("description", ""))

                item = ContentItem(
                    id=self._generate_id("github", "trending", uid),
                    source_type=SourceType.GITHUB,
                    title=f"[Trending] {repo_name}",
                    url=link,
                    content=description,
                    author=repo_name.split("/")[0] if "/" in repo_name else "",
                    published_at=datetime.now(timezone.utc),
                    metadata={"subtype": "trending", "repo": repo_name},
                )
                items.append(item)

            logger.info("GitHub Trending: fetched %d repos", len(items))

        except httpx.HTTPError as e:
            logger.warning("GitHub Trending RSS error: %s", e)
        except Exception as e:
            logger.warning("GitHub Trending parse error: %s", e)

        return items

    async def _fetch_releases(
        self, owner: str, repo: str, since: datetime
    ) -> list[ContentItem]:
        url = f"{self.api_base}/repos/{owner}/{repo}/releases"
        items: list[ContentItem] = []

        try:
            headers = self._get_headers()
            response = await self.client.get(
                url, headers=headers, follow_redirects=True, timeout=30.0
            )
            response.raise_for_status()
            releases = response.json()

            for release in releases:
                published_at = datetime.fromisoformat(
                    release["published_at"].replace("Z", "+00:00")
                )
                if published_at < since:
                    continue

                item = ContentItem(
                    id=self._generate_id(
                        "github", "release", str(release["id"])
                    ),
                    source_type=SourceType.GITHUB,
                    title=f"{owner}/{repo} released {release['tag_name']}",
                    url=release["html_url"],
                    content=release.get("body", "")[:2000],
                    author=release["author"]["login"],
                    published_at=published_at,
                    metadata={
                        "subtype": "release",
                        "repo": f"{owner}/{repo}",
                        "tag": release["tag_name"],
                        "prerelease": release.get("prerelease", False),
                    },
                )
                items.append(item)

            logger.info(
                "GitHub Releases [%s/%s]: fetched %d", owner, repo, len(items)
            )

        except httpx.HTTPError as e:
            logger.warning("GitHub Releases [%s/%s] error: %s", owner, repo, e)

        return items

    def _get_headers(self) -> dict:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "XD-AIGC-News-Aggregator",
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers
