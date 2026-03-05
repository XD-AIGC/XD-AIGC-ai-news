"""Bilibili video collector using the Bilibili API directly."""

import logging
from datetime import datetime, timezone
from hashlib import md5

import httpx

from collectors.base import BaseScraper, ContentItem, SourceType

logger = logging.getLogger(__name__)

APP_SPACE_API = "https://app.bilibili.com/x/v2/space/archive"

BILIBILI_HEADERS = {
    "User-Agent": "Mozilla/5.0 BiliDroid/7.85.0 (bbcallen@gmail.com)",
    "Referer": "https://www.bilibili.com",
}


class BilibiliCollector(BaseScraper):
    """Collect videos from Bilibili UP主 via API (direct, no proxy)."""

    def __init__(self, config: dict, http_client: httpx.AsyncClient):
        super().__init__(config, http_client)
        self.cookie = config.get("cookie", "")
        self.users = config.get("users", [])

    async def fetch(self, since: datetime) -> list[ContentItem]:
        items: list[ContentItem] = []
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as direct_client:
            for user in self.users:
                uid = str(user["uid"])
                name = user.get("name", uid)
                try:
                    user_items = await self._fetch_user_videos(
                        direct_client, uid, name, since
                    )
                    items.extend(user_items)
                except Exception as e:
                    logger.warning("Bilibili [%s] error: %s", name, e)
        return items

    async def _fetch_user_videos(
        self, client: httpx.AsyncClient, uid: str, name: str, since: datetime
    ) -> list[ContentItem]:
        """Fetch user's recent videos via the mobile app API."""
        headers = {**BILIBILI_HEADERS}
        if self.cookie:
            headers["Cookie"] = self.cookie

        params = {
            "vmid": uid, "ps": 20, "pn": 1, "order": "pubdate",
            "build": "7850300", "mobi_app": "android", "platform": "android",
        }
        items: list[ContentItem] = []

        try:
            resp = await client.get(
                APP_SPACE_API,
                params=params,
                headers=headers,
                follow_redirects=True,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                logger.warning(
                    "Bilibili [%s] API error %s: %s",
                    name, data.get("code"), data.get("message"),
                )
                return items

            archives = data.get("data", {}).get("item", [])

            for video in archives:
                item = self._parse_video(video, name, since)
                if item:
                    items.append(item)

            logger.info("Bilibili [%s]: fetched %d items", name, len(items))

        except httpx.HTTPError as e:
            logger.warning("Bilibili [%s] HTTP error: %s", name, e)

        return items

    def _parse_video(
        self, video: dict, author_name: str, since: datetime
    ) -> ContentItem | None:
        ctime = video.get("ctime", 0) or video.get("pubdate", 0)
        if ctime:
            published_at = datetime.fromtimestamp(ctime, tz=timezone.utc)
            if published_at < since:
                return None
        else:
            published_at = None

        title = video.get("title", "")
        bvid = video.get("bvid", "")
        if not bvid:
            param = video.get("param", "")
            url = f"https://www.bilibili.com/video/av{param}" if param else ""
        else:
            url = f"https://www.bilibili.com/video/{bvid}"

        if not title or not url:
            return None

        desc = video.get("description", "") or video.get("desc", "")
        author = video.get("author", author_name) or author_name
        uid = md5(url.encode()).hexdigest()[:12]

        play = video.get("play", 0) or video.get("stat", {}).get("view", 0)
        duration = video.get("duration", "")

        return ContentItem(
            id=self._generate_id("bilibili", author_name.replace(" ", "_"), uid),
            source_type=SourceType.BILIBILI,
            title=title,
            url=url,
            content=desc,
            author=author,
            published_at=published_at,
            metadata={
                "platform": "bilibili",
                "play_count": play,
                "duration": duration,
            },
        )
