"""Feishu (Lark) bot webhook for daily digest push."""

import logging
from datetime import datetime

import httpx

from collectors.base import ContentItem

logger = logging.getLogger(__name__)

CATEGORY_COLORS = {
    "开源模型": "blue",
    "ComfyUI": "purple",
    "商用产品": "green",
    "Agent & Skills": "orange",
    "训练与部署": "red",
    "其他": "grey",
}


class FeishuBot:
    def __init__(self, webhook_url: str, proxy: str | None = None):
        self.webhook_url = webhook_url
        self.proxy = proxy

    async def send_daily_digest(
        self, items: list[ContentItem], date: str | None = None
    ) -> bool:
        """Send daily digest card to Feishu group."""
        if not self.webhook_url:
            logger.warning("Feishu: no webhook URL configured, skipping")
            return False

        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        card = self._build_card(items, date)
        return await self._send(card)

    def _build_card(self, items: list[ContentItem], date: str) -> dict:
        grouped: dict[str, list[ContentItem]] = {}
        for item in items:
            cat = item.ai_categories[0] if item.ai_categories else "其他"
            grouped.setdefault(cat, []).append(item)

        elements: list[dict] = []

        elements.append({
            "tag": "markdown",
            "content": f"**日期**: {date}  |  **共 {len(items)} 条资讯**",
        })

        elements.append({"tag": "hr"})

        for category in [
            "开源模型", "ComfyUI", "商用产品",
            "Agent & Skills", "训练与部署", "其他",
        ]:
            cat_items = grouped.get(category, [])
            if not cat_items:
                continue

            color = CATEGORY_COLORS.get(category, "grey")
            elements.append({
                "tag": "markdown",
                "content": f"<font color='{color}'>**{category}** ({len(cat_items)}条)</font>",
            })

            lines: list[str] = []
            for item in cat_items[:10]:
                score_str = f" ⭐{item.ai_score:.0f}" if item.ai_score else ""
                summary = ""
                if item.ai_summary:
                    summary = f"\n  > {item.ai_summary[:100]}"
                lines.append(
                    f"• [{item.title[:60]}]({item.url}){score_str}"
                    f" *({item.source_type.value})*{summary}"
                )

            if len(cat_items) > 10:
                lines.append(f"  ...还有 {len(cat_items) - 10} 条")

            elements.append({
                "tag": "markdown",
                "content": "\n".join(lines),
            })

            elements.append({"tag": "hr"})

        return {
            "msg_type": "interactive",
            "card": {
                "config": {"wide_screen_mode": True, "enable_forward": True},
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"🤖 AI 资讯日报 - {date}",
                    },
                    "template": "blue",
                },
                "elements": elements,
            },
        }

    async def _send(self, payload: dict) -> bool:
        client_kwargs: dict = {"timeout": httpx.Timeout(30.0)}
        if self.proxy:
            client_kwargs["proxy"] = self.proxy

        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()

                if data.get("code") == 0 or data.get("StatusCode") == 0:
                    logger.info("Feishu: message sent successfully")
                    return True
                else:
                    logger.warning("Feishu: API error: %s", data)
                    return False

        except httpx.HTTPError as e:
            logger.error("Feishu: request failed: %s", e)
            return False
