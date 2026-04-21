"""AI-powered scoring, classification, and summarization using LLM."""

import json
import logging

import httpx

from collectors.base import ContentItem

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个专业的 AI 科技资讯评审专家，专注于以下领域：
- 开源模型 (Stable Diffusion, Flux, HunyuanVideo, CogView, Wan, LoRA, Hugging Face)
- ComfyUI (节点, 工作流, 插件)
- 商用产品 (Lovart, Gemini, GPT, OpenAI, Claude, Anthropic, Midjourney, DALL-E, Sora, Runway)
- Agent & Skills (AI Agent, MCP, tool use, function calling, 自动化)
- 训练与部署 (fine-tune, LoRA, RLHF, 推理优化, 量化, 部署)

请对每条资讯进行评分和分析。评分标准：
- 9-10: 重大突破、范式转变、行业重大公告
- 7-8: 重要进展，值得立即关注的技术深度内容
- 5-6: 有趣但不紧急，增量改进
- 3-4: 低优先级，通用或常规内容
- 0-2: 噪音，不相关或低质量"""

USER_PROMPT_TEMPLATE = """分析以下资讯，返回 JSON：

标题: {title}
来源: {source}
作者: {author}
链接: {url}
内容: {content}

请返回以下 JSON 格式（不要包含 markdown 代码块标记）：
{{
  "score": <0-10的浮点数>,
  "summary": "<2-3句中文摘要>",
  "categories": [<从以下选择: "开源模型", "ComfyUI", "商用产品", "Agent & Skills", "训练与部署", "其他">],
  "tags": ["<3-5个相关标签>"],
  "reason": "<评分理由，一句话>"
}}"""


class AIScorer:
    """Score, classify and summarize items using LLM."""

    def __init__(self, config: dict):
        self.model = config.get("model", "gpt-4o-mini")
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", "https://api.openai.com/v1")
        self.temperature = config.get("temperature", 0.3)
        self.threshold = config.get("score_threshold", 6.0)
        self.proxy = config.get("proxy")
        self.scoring_prompts: dict[str, str] = config.get("scoring_prompts", {})

    def _system_prompt_for(self, item: ContentItem) -> str:
        """Pick the theme-specific prompt, falling back to ai prompt, then legacy SYSTEM_PROMPT."""
        if not self.scoring_prompts:
            return SYSTEM_PROMPT
        theme_key = item.theme.value if hasattr(item.theme, "value") else str(item.theme)
        if theme_key in self.scoring_prompts:
            return self.scoring_prompts[theme_key]
        # Fallback: use ai prompt if defined, else legacy
        if "ai" in self.scoring_prompts:
            logger.warning(
                "No scoring prompt for theme '%s', falling back to 'ai'", theme_key,
            )
            return self.scoring_prompts["ai"]
        return SYSTEM_PROMPT

    async def process_items(
        self, items: list[ContentItem], skip_scored: bool = True
    ) -> list[ContentItem]:
        """Score all items. Modifies items in-place and returns them."""
        if not self.api_key:
            logger.warning("AI Scorer: no API key, skipping AI processing")
            return items

        processed = 0
        errors = 0

        for item in items:
            if skip_scored and item.ai_score is not None:
                continue
            try:
                await self._score_item(item)
                processed += 1
            except Exception as e:
                logger.warning("AI scoring failed for [%s]: %s", item.title[:50], e)
                item.ai_score = 0.0
                item.ai_summary = item.title
                item.ai_categories = ["其他"]
                errors += 1

        logger.info(
            "AI Scorer: processed %d items (%d errors)", processed, errors
        )
        return items

    def filter_by_score(self, items: list[ContentItem]) -> list[ContentItem]:
        """Filter items by score threshold."""
        before = len(items)
        filtered = [
            item for item in items
            if item.ai_score is not None and item.ai_score >= self.threshold
        ]
        logger.info(
            "AI Filter: %d -> %d items (threshold %.1f)",
            before, len(filtered), self.threshold,
        )
        return filtered

    async def _score_item(self, item: ContentItem) -> None:
        content_preview = item.content[:1000] if item.content else ""
        if "--- Top Comments ---" in content_preview:
            main_text, _ = content_preview.split("--- Top Comments ---", 1)
            content_preview = main_text.strip()[:800]

        system_prompt = self._system_prompt_for(item)
        user_prompt = USER_PROMPT_TEMPLATE.format(
            title=item.title,
            source=item.source_type.value,
            author=item.author or "Unknown",
            url=item.url,
            content=content_preview,
        )

        client_kwargs: dict = {"timeout": httpx.Timeout(60.0)}
        if self.proxy:
            client_kwargs["proxy"] = self.proxy

        async with httpx.AsyncClient(**client_kwargs) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": self.temperature,
                    "max_tokens": 512,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        content_str = data["choices"][0]["message"]["content"].strip()
        result = self._parse_json(content_str)

        item.ai_score = float(result.get("score", 0))
        item.ai_summary = result.get("summary", item.title)
        item.ai_categories = result.get("categories", ["其他"])
        item.ai_tags = result.get("tags", [])

    @staticmethod
    def _parse_json(text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.strip().startswith("```") and not in_block:
                    in_block = True
                    continue
                elif line.strip() == "```":
                    break
                elif in_block:
                    json_lines.append(line)
            text = "\n".join(json_lines)

        return json.loads(text)
