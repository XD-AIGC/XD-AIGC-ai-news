"""Bilibili video collector using wbi-signed API."""

import functools
import logging
import time
import urllib.parse
from datetime import datetime, timezone
from hashlib import md5

import httpx

from collectors.base import BaseScraper, ContentItem, SourceType, Theme

logger = logging.getLogger(__name__)

WBI_NAV_API = "https://api.bilibili.com/x/web-interface/nav"
WBI_SEARCH_API = "https://api.bilibili.com/x/space/wbi/arc/search"

BILIBILI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
    "Origin": "https://www.bilibili.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]


def _get_mixin_key(raw: str) -> str:
    return functools.reduce(lambda s, i: s + raw[i], MIXIN_KEY_ENC_TAB, "")[:32]


def _sign_params(params: dict, img_key: str, sub_key: str) -> dict:
    """Add wbi signature (wts + w_rid) to request parameters."""
    mixin_key = _get_mixin_key(img_key + sub_key)
    params["wts"] = int(time.time())
    params = dict(sorted(params.items()))
    filtered = {
        k: "".join(c for c in str(v) if c not in "!'()*")
        for k, v in params.items()
    }
    query = urllib.parse.urlencode(filtered)
    params["w_rid"] = md5((query + mixin_key).encode()).hexdigest()
    return params


class BilibiliCollector(BaseScraper):
    """Collect videos from Bilibili UP主 via wbi-signed API (no proxy)."""

    def __init__(self, config: dict, http_client: httpx.AsyncClient):
        super().__init__(config, http_client)
        self.cookie = config.get("cookie", "")
        self.users = config.get("users", [])
        self._img_key: str = ""
        self._sub_key: str = ""

    async def fetch(self, since: datetime) -> list[ContentItem]:
        items: list[ContentItem] = []
        headers = {**BILIBILI_HEADERS}
        if self.cookie:
            headers["Cookie"] = self.cookie

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0), headers=headers
        ) as client:
            await self._refresh_wbi_keys(client)
            if not self._img_key:
                logger.error("Bilibili: failed to get wbi keys, skipping")
                return items

            for user in self.users:
                uid = str(user["uid"])
                name = user.get("name", uid)
                theme = Theme(user.get("theme", "ai"))
                try:
                    user_items = await self._fetch_user_videos(
                        client, uid, name, since, theme
                    )
                    items.extend(user_items)
                except Exception as e:
                    logger.warning("Bilibili [%s] error: %s", name, e)
        return items

    async def _refresh_wbi_keys(self, client: httpx.AsyncClient) -> None:
        try:
            resp = await client.get(WBI_NAV_API, follow_redirects=True)
            resp.raise_for_status()
            data = resp.json()
            wbi_img = data.get("data", {}).get("wbi_img", {})
            img_url = wbi_img.get("img_url", "")
            sub_url = wbi_img.get("sub_url", "")
            self._img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
            self._sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
            logger.debug("Bilibili wbi keys refreshed")
        except Exception as e:
            logger.warning("Bilibili wbi key fetch failed: %s", e)

    async def _fetch_user_videos(
        self, client: httpx.AsyncClient, uid: str, name: str, since: datetime,
        theme: Theme = Theme("ai"),
    ) -> list[ContentItem]:
        """Fetch user's recent videos via wbi-signed API."""
        params = {"mid": uid, "ps": 20, "pn": 1, "order": "pubdate"}
        signed = _sign_params(params, self._img_key, self._sub_key)
        items: list[ContentItem] = []

        try:
            resp = await client.get(
                WBI_SEARCH_API,
                params=signed,
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

            vlist = (
                data.get("data", {})
                .get("list", {})
                .get("vlist", [])
            )

            for video in vlist:
                item = self._parse_video(video, name, since, theme)
                if item:
                    items.append(item)

            logger.info("Bilibili [%s]: fetched %d items", name, len(items))

        except httpx.HTTPError as e:
            logger.warning("Bilibili [%s] HTTP error: %s", name, e)

        return items

    def _parse_video(
        self, video: dict, author_name: str, since: datetime,
        theme: Theme = Theme("ai"),
    ) -> ContentItem | None:
        created = video.get("created", 0)
        if created:
            published_at = datetime.fromtimestamp(created, tz=timezone.utc)
            if published_at < since:
                return None
        else:
            published_at = None

        title = video.get("title", "")
        bvid = video.get("bvid", "")
        if not bvid:
            aid = video.get("aid", "")
            url = f"https://www.bilibili.com/video/av{aid}" if aid else ""
        else:
            url = f"https://www.bilibili.com/video/{bvid}"

        if not title or not url:
            return None

        desc = video.get("description", "")
        author = video.get("author", author_name) or author_name
        uid = md5(url.encode()).hexdigest()[:12]

        play = video.get("play", 0)
        length = video.get("length", "")

        return ContentItem(
            id=self._generate_id("bilibili", author_name.replace(" ", "_"), uid),
            source_type=SourceType.BILIBILI,
            title=title,
            url=url,
            content=desc,
            author=author,
            published_at=published_at,
            theme=theme,
            metadata={
                "platform": "bilibili",
                "play_count": play,
                "duration": length,
            },
        )
