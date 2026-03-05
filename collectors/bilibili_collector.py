"""Bilibili video collector using the Bilibili API directly."""

import logging
from datetime import datetime, timezone
from hashlib import md5

import httpx

from collectors.base import BaseScraper, ContentItem, SourceType

logger = logging.getLogger(__name__)

SPACE_API = "https://api.bilibili.com/x/space/wbi/arc/search"
NAV_API = "https://api.bilibili.com/x/web-interface/nav"
DYNAMIC_API = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"

BILIBILI_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
    "Origin": "https://www.bilibili.com",
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
                    user_items = await self._fetch_user_dynamic(
                        direct_client, uid, name, since
                    )
                    items.extend(user_items)
                except Exception as e:
                    logger.warning("Bilibili [%s] error: %s", name, e)
        return items

    async def _fetch_user_dynamic(
        self, client: httpx.AsyncClient, uid: str, name: str, since: datetime
    ) -> list[ContentItem]:
        """Fetch user's recent dynamics (videos, articles, etc.)."""
        headers = {**BILIBILI_HEADERS}
        if self.cookie:
            headers["Cookie"] = self.cookie

        params = {"host_mid": uid}
        items: list[ContentItem] = []

        try:
            resp = await client.get(
                DYNAMIC_API,
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

            dynamic_list = (
                data.get("data", {}).get("items", [])
            )

            for dyn in dynamic_list:
                item = self._parse_dynamic(dyn, name, since)
                if item:
                    items.append(item)

            logger.info("Bilibili [%s]: fetched %d items", name, len(items))

        except httpx.HTTPError as e:
            logger.warning("Bilibili [%s] HTTP error: %s", name, e)

        return items

    def _parse_dynamic(
        self, dyn: dict, author_name: str, since: datetime
    ) -> ContentItem | None:
        modules = dyn.get("modules", {})
        author_mod = modules.get("module_author", {})
        major_mod = modules.get("module_dynamic", {}).get("major")

        pub_ts = author_mod.get("pub_ts", 0)
        if pub_ts:
            published_at = datetime.fromtimestamp(pub_ts, tz=timezone.utc)
            if published_at < since:
                return None
        else:
            published_at = None

        dyn_type = dyn.get("type", "")
        title = ""
        url = ""
        content = ""

        if dyn_type == "DYNAMIC_TYPE_AV" and major_mod:
            archive = major_mod.get("archive", {})
            title = archive.get("title", "")
            bvid = archive.get("bvid", "")
            url = f"https://www.bilibili.com/video/{bvid}" if bvid else ""
            content = archive.get("desc", "")
            if not content:
                content = modules.get("module_dynamic", {}).get("desc", {}).get("text", "")

        elif dyn_type == "DYNAMIC_TYPE_ARTICLE" and major_mod:
            article = major_mod.get("article", {})
            title = article.get("title", "")
            article_id = article.get("id", "")
            url = f"https://www.bilibili.com/read/cv{article_id}" if article_id else ""
            content = ", ".join(article.get("desc", ""))

        elif dyn_type == "DYNAMIC_TYPE_DRAW":
            desc_mod = modules.get("module_dynamic", {}).get("desc", {})
            text = desc_mod.get("text", "")
            title = text[:80] if text else "动态图片"
            content = text
            dyn_id = dyn.get("id_str", "")
            url = f"https://t.bilibili.com/{dyn_id}" if dyn_id else ""

        elif dyn_type == "DYNAMIC_TYPE_WORD":
            desc_mod = modules.get("module_dynamic", {}).get("desc", {})
            text = desc_mod.get("text", "")
            title = text[:80] if text else "文字动态"
            content = text
            dyn_id = dyn.get("id_str", "")
            url = f"https://t.bilibili.com/{dyn_id}" if dyn_id else ""

        else:
            desc_mod = modules.get("module_dynamic", {}).get("desc", {})
            text = desc_mod.get("text", "")
            title = text[:80] if text else f"动态 ({dyn_type})"
            content = text
            dyn_id = dyn.get("id_str", "")
            url = f"https://t.bilibili.com/{dyn_id}" if dyn_id else ""

        if not title and not content:
            return None
        if not url:
            return None

        uid = md5(url.encode()).hexdigest()[:12]
        author = author_mod.get("name", author_name)

        return ContentItem(
            id=self._generate_id("bilibili", author_name.replace(" ", "_"), uid),
            source_type=SourceType.BILIBILI,
            title=title,
            url=url,
            content=content,
            author=author,
            published_at=published_at,
            metadata={"platform": "bilibili", "dynamic_type": dyn_type},
        )
