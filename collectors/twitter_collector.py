"""Twitter/X collector using the web API with auth_token cookie."""

import logging
from datetime import datetime, timezone
from hashlib import md5

import httpx

from collectors.base import BaseScraper, ContentItem, SourceType

logger = logging.getLogger(__name__)

BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "=1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

USER_TIMELINE_API = "https://api.twitter.com/1.1/statuses/user_timeline.json"

TWITTER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Authorization": f"Bearer {BEARER_TOKEN}",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


def _get_csrf_token(auth_token: str) -> str:
    return md5(auth_token.encode()).hexdigest()[:32]


class TwitterCollector(BaseScraper):
    """Collect tweets from X/Twitter users via web API."""

    def __init__(self, config: dict, http_client: httpx.AsyncClient):
        super().__init__(config, http_client)
        self.auth_token = config.get("auth_token", "")
        self.users = config.get("users", [])
        self.proxy = config.get("proxy", "")

    async def fetch(self, since: datetime) -> list[ContentItem]:
        if not self.auth_token:
            logger.warning("Twitter: no auth_token configured, skipping")
            return []

        items: list[ContentItem] = []
        csrf = _get_csrf_token(self.auth_token)
        headers = {
            **TWITTER_HEADERS,
            "Cookie": f"auth_token={self.auth_token}; ct0={csrf}",
            "X-Csrf-Token": csrf,
        }

        client_kwargs: dict = {
            "timeout": httpx.Timeout(30.0),
            "headers": headers,
        }
        if self.proxy:
            client_kwargs["proxy"] = self.proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            for user_cfg in self.users:
                screen_name = user_cfg["id"]
                name = user_cfg.get("name", screen_name)
                try:
                    user_items = await self._fetch_user_timeline(
                        client, screen_name, name, since
                    )
                    items.extend(user_items)
                except Exception as e:
                    logger.warning("Twitter [%s] error: %s", name, e)

        return items

    async def _fetch_user_timeline(
        self,
        client: httpx.AsyncClient,
        screen_name: str,
        name: str,
        since: datetime,
    ) -> list[ContentItem]:
        """Fetch user's recent tweets via v1.1 REST API."""
        params = {
            "screen_name": screen_name,
            "count": 20,
            "exclude_replies": "false",
            "include_rts": "false",
            "tweet_mode": "extended",
        }

        items: list[ContentItem] = []
        try:
            resp = await client.get(
                USER_TIMELINE_API,
                params=params,
                follow_redirects=True,
            )
            resp.raise_for_status()
            tweets = resp.json()

            if not isinstance(tweets, list):
                logger.warning(
                    "Twitter [%s] unexpected response: %s",
                    name, str(tweets)[:200],
                )
                return items

            for tweet in tweets:
                item = self._parse_tweet(tweet, screen_name, name, since)
                if item:
                    items.append(item)

            logger.info("Twitter [%s]: fetched %d items", name, len(items))

        except httpx.HTTPError as e:
            logger.warning("Twitter [%s] HTTP error: %s", name, e)

        return items

    def _parse_tweet(
        self,
        tweet: dict,
        screen_name: str,
        name: str,
        since: datetime,
    ) -> ContentItem | None:
        created_str = tweet.get("created_at", "")
        if created_str:
            try:
                published_at = datetime.strptime(
                    created_str, "%a %b %d %H:%M:%S %z %Y"
                )
                if published_at < since:
                    return None
            except ValueError:
                published_at = None
        else:
            published_at = None

        full_text = tweet.get("full_text", "") or tweet.get("text", "")
        tweet_id = tweet.get("id_str", "")
        user_sn = tweet.get("user", {}).get("screen_name", screen_name)
        url = f"https://x.com/{user_sn}/status/{tweet_id}" if tweet_id else ""

        if not full_text or not url:
            return None

        title = full_text[:120].replace("\n", " ")
        if len(full_text) > 120:
            title += "..."

        uid = md5(url.encode()).hexdigest()[:12]

        return ContentItem(
            id=self._generate_id("twitter", screen_name, uid),
            source_type=SourceType.TWITTER,
            title=title,
            url=url,
            content=full_text,
            author=name,
            published_at=published_at,
            metadata={
                "platform": "twitter",
                "retweet_count": tweet.get("retweet_count", 0),
                "favorite_count": tweet.get("favorite_count", 0),
            },
        )
