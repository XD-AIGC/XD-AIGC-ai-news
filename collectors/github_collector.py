"""GitHub scraper: explosive-growth repos via Search API + watched repo releases."""

import logging
import os
from datetime import datetime, timedelta, timezone
from hashlib import md5

import httpx

from collectors.base import BaseScraper, ContentItem, SourceType

logger = logging.getLogger(__name__)


class GitHubCollector(BaseScraper):
    """Detect repos with explosive star growth + watched repo releases."""

    def __init__(self, config: dict, http_client: httpx.AsyncClient):
        super().__init__(config, http_client)
        self.token = os.getenv("GITHUB_TOKEN")
        self.api_base = "https://api.github.com"

    async def fetch(self, since: datetime) -> list[ContentItem]:
        items: list[ContentItem] = []

        # 1. Explosive-growth repos via Search API
        explosive_cfg = self.config.get("explosive", {})
        if explosive_cfg.get("enabled", True):
            items.extend(await self._fetch_explosive(explosive_cfg))

        # 2. Watched repo releases (keep existing logic)
        for repo_cfg in self.config.get("watch_repos", []):
            items.extend(
                await self._fetch_releases(
                    repo_cfg["owner"], repo_cfg["repo"], since
                )
            )

        return items

    async def _fetch_explosive(self, cfg: dict) -> list[ContentItem]:
        """Find repos with explosive star growth in the last N days.

        Strategy: Search GitHub for repos created/pushed recently with
        high star counts. Calculate stars_per_day as growth rate.
        A repo created 10 days ago with 5K stars = 500 stars/day (explosive).
        """
        lookback_days = cfg.get("lookback_days", 15)
        min_stars = cfg.get("min_stars", 100)
        top_n = cfg.get("top_n", 15)
        queries = cfg.get("search_queries", [])

        if not queries:
            queries = [
                "topic:ai",
                "topic:machine-learning",
                "topic:llm",
            ]

        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        all_repos: list[dict] = []
        seen_ids: set[int] = set()

        for query in queries:
            try:
                repos = await self._search_repos(
                    query, cutoff_str, min_stars
                )
                for repo in repos:
                    if repo["id"] not in seen_ids:
                        seen_ids.add(repo["id"])
                        all_repos.append(repo)
            except Exception as e:
                logger.warning("GitHub Search [%s] error: %s", query, e)

        # Calculate growth rate and sort
        for repo in all_repos:
            created = datetime.fromisoformat(
                repo["created_at"].replace("Z", "+00:00")
            )
            age_days = max((datetime.now(timezone.utc) - created).days, 1)
            repo["_stars_per_day"] = repo["stargazers_count"] / age_days
            repo["_age_days"] = age_days

        all_repos.sort(key=lambda r: r["_stars_per_day"], reverse=True)
        top_repos = all_repos[:top_n]

        items: list[ContentItem] = []
        for repo in top_repos:
            stars = repo["stargazers_count"]
            spd = repo["_stars_per_day"]
            age = repo["_age_days"]
            full_name = repo["full_name"]

            title = (
                f"[{stars:,} stars in {age}d, +{spd:.0f}/day] "
                f"{full_name}"
            )

            description = repo.get("description") or ""
            topics = repo.get("topics", [])
            language = repo.get("language") or ""

            content_parts = [description]
            if topics:
                content_parts.append(f"Topics: {', '.join(topics)}")
            if language:
                content_parts.append(f"Language: {language}")
            content_parts.append(
                f"Stars: {stars:,} | Forks: {repo.get('forks_count', 0):,} | "
                f"Growth: +{spd:.0f} stars/day"
            )

            uid = md5(repo["html_url"].encode()).hexdigest()[:12]

            items.append(ContentItem(
                id=self._generate_id("github", "explosive", uid),
                source_type=SourceType.GITHUB,
                title=title,
                url=repo["html_url"],
                content="\n".join(content_parts),
                author=repo["owner"]["login"],
                published_at=datetime.fromisoformat(
                    repo["created_at"].replace("Z", "+00:00")
                ),
                metadata={
                    "subtype": "explosive",
                    "repo": full_name,
                    "stars": stars,
                    "stars_per_day": round(spd, 1),
                    "age_days": age,
                    "forks": repo.get("forks_count", 0),
                    "language": language,
                    "topics": topics,
                },
            ))

        logger.info(
            "GitHub Explosive: %d candidates -> top %d "
            "(lookback %dd, min_stars %d)",
            len(all_repos), len(items), lookback_days, min_stars,
        )
        return items

    async def _search_repos(
        self, query: str, created_since: str, min_stars: int
    ) -> list[dict]:
        """Call GitHub Search API for repos matching query."""
        q = f"{query} created:>{created_since} stars:>={min_stars}"
        url = f"{self.api_base}/search/repositories"

        headers = self._get_headers()
        response = await self.client.get(
            url,
            headers=headers,
            params={
                "q": q,
                "sort": "stars",
                "order": "desc",
                "per_page": 30,
            },
            follow_redirects=True,
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

        logger.debug(
            "GitHub Search [%s]: %d results (total: %d)",
            query, len(data.get("items", [])), data.get("total_count", 0),
        )
        return data.get("items", [])

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
