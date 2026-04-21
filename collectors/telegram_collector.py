"""Telegram public channel scraper via web preview."""

import asyncio
import logging
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from collectors.base import BaseScraper, ContentItem, SourceType, Theme

logger = logging.getLogger(__name__)

TELEGRAM_WEB_BASE = "https://t.me/s"
USER_AGENT = "Mozilla/5.0 (compatible; XD-AIGC-News/1.0)"


class TelegramCollector(BaseScraper):
    """Scraper for Telegram public channels via t.me/s/ web preview."""

    async def fetch(self, since: datetime) -> list[ContentItem]:
        if not self.config.get("enabled", True):
            return []

        tasks = []
        for ch_cfg in self.config.get("channels", []):
            tasks.append(self._fetch_channel(ch_cfg, since))

        if not tasks:
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)
        items: list[ContentItem] = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("Telegram fetch error: %s", result)
            elif isinstance(result, list):
                items.extend(result)
        return items

    async def _fetch_channel(
        self, cfg: dict, since: datetime
    ) -> list[ContentItem]:
        channel = cfg["channel"]
        name = cfg.get("name", channel)
        fetch_limit = cfg.get("fetch_limit", 20)
        theme = Theme(cfg.get("theme", "ai"))

        url = f"{TELEGRAM_WEB_BASE}/{channel}"
        headers = {"User-Agent": USER_AGENT}

        try:
            resp = await self.client.get(
                url, headers=headers, follow_redirects=True, timeout=120.0
            )
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 5))
                logger.warning(
                    "Telegram rate limited for %s, retrying after %ds",
                    channel,
                    retry_after,
                )
                await asyncio.sleep(retry_after)
                resp = await self.client.get(
                    url, headers=headers, follow_redirects=True, timeout=120.0
                )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning("Telegram [%s] request failed: %s", name, e)
            return []

        items = self._parse_html(resp.text, channel, name, since, fetch_limit, theme)
        logger.info("Telegram [%s]: fetched %d messages", name, len(items))
        return items

    def _parse_html(
        self,
        html: str,
        channel: str,
        name: str,
        since: datetime,
        fetch_limit: int,
        theme: Theme = Theme("ai"),
    ) -> list[ContentItem]:
        soup = BeautifulSoup(html, "html.parser")
        messages = soup.select("div.tgme_widget_message[data-post]")

        items: list[ContentItem] = []
        for msg in messages[-fetch_limit:]:
            item = self._parse_message(msg, channel, name, since, theme)
            if item:
                items.append(item)
        return items

    def _parse_message(
        self,
        msg_el,
        channel: str,
        name: str,
        since: datetime,
        theme: Theme = Theme("ai"),
    ) -> ContentItem | None:
        data_post = msg_el.get("data-post", "")
        msg_id = data_post.split("/")[-1] if "/" in data_post else data_post
        if not msg_id:
            return None

        time_el = msg_el.select_one("time[datetime]")
        if not time_el:
            return None
        try:
            published_at = datetime.fromisoformat(
                time_el["datetime"].replace("Z", "+00:00")
            )
        except (ValueError, KeyError):
            return None

        if published_at < since:
            return None

        text_el = msg_el.select_one("div.tgme_widget_message_text")
        if not text_el:
            return None

        for br in text_el.find_all("br"):
            br.replace_with("\n")
        text = text_el.get_text(separator="").strip()
        if not text:
            return None

        title = self._make_title(text)

        msg_url = f"https://t.me/{channel}/{msg_id}"
        canonical_url = msg_url
        for a in text_el.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "t.me" not in href:
                canonical_url = href
                break

        return ContentItem(
            id=self._generate_id("telegram", channel, msg_id),
            source_type=SourceType.TELEGRAM,
            title=title,
            url=canonical_url,
            content=text,
            author=name,
            published_at=published_at,
            theme=theme,
            metadata={"msg_url": msg_url, "channel": channel},
        )

    @staticmethod
    def _make_title(text: str) -> str:
        first_para = text.split("\n\n")[0].replace("\n", " ").strip()
        if len(first_para) <= 80:
            return first_para
        match = re.search(r"[。！？]", first_para[:80])
        if match:
            return first_para[: match.end()]
        return first_para[:80] + "..."
