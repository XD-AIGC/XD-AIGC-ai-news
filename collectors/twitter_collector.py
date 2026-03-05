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

USER_BY_SCREEN_NAME = "https://x.com/i/api/graphql/xmU6X_CKcnQ5lSrCbAmJsg/UserByScreenName"
USER_TWEETS = "https://x.com/i/api/graphql/Y9WM4Id6UcGFE8Z-hbnixw/UserTweets"

TWITTER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Authorization": f"Bearer {BEARER_TOKEN}",
    "X-Twitter-Active-User": "yes",
    "X-Twitter-Client-Language": "en",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://x.com/",
    "Origin": "https://x.com",
}

FEATURES_USER = (
    '{"hidden_profile_subscriptions_enabled":true,'
    '"rweb_tipjar_consumption_enabled":true,'
    '"responsive_web_graphql_exclude_directive_enabled":true,'
    '"verified_phone_label_enabled":false,'
    '"subscriptions_verification_info_is_identity_verified_enabled":true,'
    '"subscriptions_verification_info_verified_since_enabled":true,'
    '"highlights_tweets_tab_ui_enabled":true,'
    '"responsive_web_twitter_article_notes_tab_enabled":true,'
    '"subscriptions_feature_can_gift_premium":true,'
    '"creator_subscriptions_tweet_preview_api_enabled":true,'
    '"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,'
    '"responsive_web_graphql_timeline_navigation_enabled":true}'
)

FEATURES_TWEETS = (
    '{"rweb_tipjar_consumption_enabled":true,'
    '"responsive_web_graphql_exclude_directive_enabled":true,'
    '"verified_phone_label_enabled":false,'
    '"creator_subscriptions_tweet_preview_api_enabled":true,'
    '"responsive_web_graphql_timeline_navigation_enabled":true,'
    '"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,'
    '"communities_web_enable_tweet_community_results_fetch":true,'
    '"c9s_tweet_anatomy_moderator_badge_enabled":true,'
    '"articles_preview_enabled":true,'
    '"responsive_web_edit_tweet_api_enabled":true,'
    '"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,'
    '"view_counts_everywhere_api_enabled":true,'
    '"longform_notetweets_consumption_enabled":true,'
    '"responsive_web_twitter_article_tweet_consumption_enabled":true,'
    '"tweet_awards_web_tipping_enabled":false,'
    '"creator_subscriptions_quote_tweet_preview_enabled":false,'
    '"freedom_of_speech_not_reach_fetch_enabled":true,'
    '"standardized_nudges_misinfo":true,'
    '"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,'
    '"rweb_video_timestamps_enabled":true,'
    '"longform_notetweets_rich_text_read_enabled":true,'
    '"longform_notetweets_inline_media_enabled":true,'
    '"responsive_web_enhance_cards_enabled":false}'
)


def _get_csrf_token(auth_token: str) -> str:
    """Generate a csrf token (ct0) from auth_token - use a random hex."""
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
                    user_items = await self._fetch_user_tweets(
                        client, screen_name, name, since
                    )
                    items.extend(user_items)
                except Exception as e:
                    logger.warning("Twitter [%s] error: %s", name, e)

        return items

    async def _get_user_id(
        self, client: httpx.AsyncClient, screen_name: str
    ) -> str | None:
        params = {
            "variables": f'{{"screen_name":"{screen_name}","withSafetyModeUserFields":true}}',
            "features": FEATURES_USER,
            "fieldToggles": '{"withAuxiliaryUserLabels":false}',
        }
        try:
            resp = await client.get(
                USER_BY_SCREEN_NAME, params=params, follow_redirects=True
            )
            resp.raise_for_status()
            data = resp.json()
            return data["data"]["user"]["result"]["rest_id"]
        except Exception as e:
            logger.warning("Twitter user lookup [%s] failed: %s", screen_name, e)
            return None

    async def _fetch_user_tweets(
        self,
        client: httpx.AsyncClient,
        screen_name: str,
        name: str,
        since: datetime,
    ) -> list[ContentItem]:
        user_id = await self._get_user_id(client, screen_name)
        if not user_id:
            return []

        variables = (
            f'{{"userId":"{user_id}","count":20,'
            f'"includePromotedContent":false,'
            f'"withQuickPromoteEligibilityTweetFields":true,'
            f'"withVoice":true,"withV2Timeline":true}}'
        )
        params = {
            "variables": variables,
            "features": FEATURES_TWEETS,
        }

        items: list[ContentItem] = []
        try:
            resp = await client.get(
                USER_TWEETS, params=params, follow_redirects=True
            )
            resp.raise_for_status()
            data = resp.json()

            timeline = (
                data.get("data", {})
                .get("user", {})
                .get("result", {})
                .get("timeline_v2", {})
                .get("timeline", {})
                .get("instructions", [])
            )

            for instruction in timeline:
                entries = instruction.get("entries", [])
                for entry in entries:
                    item = self._parse_entry(entry, screen_name, name, since)
                    if item:
                        items.append(item)

            logger.info("Twitter [%s]: fetched %d items", name, len(items))

        except httpx.HTTPError as e:
            logger.warning("Twitter [%s] HTTP error: %s", name, e)

        return items

    def _parse_entry(
        self,
        entry: dict,
        screen_name: str,
        name: str,
        since: datetime,
    ) -> ContentItem | None:
        content = entry.get("content", {})
        if content.get("entryType") != "TimelineTimelineItem":
            return None

        tweet_result = (
            content.get("itemContent", {})
            .get("tweet_results", {})
            .get("result", {})
        )

        if tweet_result.get("__typename") == "TweetWithVisibilityResults":
            tweet_result = tweet_result.get("tweet", {})

        legacy = tweet_result.get("legacy", {})
        if not legacy:
            return None

        created_str = legacy.get("created_at", "")
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

        full_text = legacy.get("full_text", "")
        tweet_id = legacy.get("id_str", "")
        url = f"https://x.com/{screen_name}/status/{tweet_id}" if tweet_id else ""

        if not full_text or not url:
            return None

        title = full_text[:120].replace("\n", " ")
        if len(full_text) > 120:
            title += "..."

        uid = md5(url.encode()).hexdigest()[:12]

        retweet_count = legacy.get("retweet_count", 0)
        favorite_count = legacy.get("favorite_count", 0)

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
                "retweet_count": retweet_count,
                "favorite_count": favorite_count,
            },
        )
