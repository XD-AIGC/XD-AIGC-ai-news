"""Generate Doraemon-style manga comics from weekly AI news."""

import asyncio
import base64
import json
import logging
from pathlib import Path

import httpx

from collectors.base import ContentItem

logger = logging.getLogger(__name__)

SCRIPT_SYSTEM_PROMPT = """你是一个漫画编剧，擅长用哆啦A梦和大雄的对话来讲述AI科技新闻。

你需要将本周的AI新闻编成3个4格漫画故事：
- 故事1（头条）：用兴奋/震撼的语气讲述本周最大新闻
- 故事2（领域动态）：用科普/对比的方式介绍多个相关事件
- 故事3（轻松吐槽）：用搞笑/讽刺的方式吐槽AI行业现象，大雄的经典抱怨+哆啦A梦的毒舌回复

角色设定：
- 哆啦A梦：博学的AI专家，解释新闻和技术，偶尔毒舌吐槽大雄
- 大雄：好奇但懒惰的普通人，提问、反应、偶尔想偷懒被拆穿

要求：
- 每个故事4格，每格有场景描述和对话
- 对话要自然有趣，像真正的漫画台词
- 故事3必须搞笑，要有反转或意想不到的笑点
- 返回 JSON 格式"""

SCRIPT_USER_TEMPLATE = """本周AI新闻Top 10（按重要性排序）：

{news_list}

本周统计：共{total}条新闻，{sources}个来源

请编写3个4格漫画故事的脚本，返回JSON格式：
{{
  "week_title": "本周一句话标题（如'AI圈又炸了'）",
  "editor_note": "编辑寄语，2-3句话总结本周",
  "stories": [
    {{
      "title": "故事标题",
      "theme": "headline|trends|comedy",
      "label": "本周头条|开源&工具|轻松一刻",
      "summary": "故事摘要，3-4句话",
      "highlights": ["亮点1", "亮点2", "亮点3"],
      "community_quotes": [
        {{"text": "引用内容", "author": "来源"}}
      ],
      "related_news": [
        {{"title": "新闻标题", "score": 9.8}}
      ],
      "panels": [
        {{
          "scene": "场景描述（英文，用于生成图片）",
          "dialogue_cn": "中文对话台词",
          "sfx": "日文音效词（如ガーン、ドキドキ）"
        }}
      ],
      "doraemon_quote": "哆啦A梦的总结金句（仅故事3需要）"
    }}
  ]
}}"""


class ComicGenerator:
    """Generate Doraemon manga comics from news data."""

    def __init__(self, config: dict):
        self.llm_model = config.get("llm_model", "gemini-2.5-flash")
        self.image_model = config.get("image_model", "nano-banana-pro-preview")
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", "https://generativelanguage.googleapis.com/v1beta/openai")
        self.gemini_api_base = "https://generativelanguage.googleapis.com/v1beta"
        self.proxy = config.get("proxy")
        self.max_concurrent = config.get("max_concurrent_images", 3)

    async def generate_script(
        self, top_items: list[ContentItem], total_count: int, source_count: int
    ) -> dict:
        """Use LLM to write comic script from top news items."""
        news_list = "\n".join(
            f"{i+1}. [{item.ai_score or 0:.1f}] {item.title}"
            f"\n   摘要: {item.ai_summary or item.title}"
            f"\n   分类: {', '.join(item.ai_categories or ['其他'])}"
            for i, item in enumerate(top_items[:10])
        )

        user_prompt = SCRIPT_USER_TEMPLATE.format(
            news_list=news_list,
            total=total_count,
            sources=source_count,
        )

        client_kwargs: dict = {"timeout": httpx.Timeout(120.0)}
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
                    "model": self.llm_model,
                    "messages": [
                        {"role": "system", "content": SCRIPT_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.8,
                    "max_tokens": 4096,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"].strip()
        return self._parse_json(content)

    async def generate_panel_image(
        self, panel: dict, story_index: int, panel_index: int
    ) -> bytes:
        """Generate a single manga panel image using Nano Banana Pro."""
        prompt = (
            f"A single manga panel in the style of Doraemon by Fujiko F. Fujio. "
            f"Black and white manga style with clean lines. "
            f"Scene: {panel['scene']}. "
            f"Speech bubble with Chinese text: \"{panel['dialogue_cn']}\". "
            f"Japanese sound effect: \"{panel.get('sfx', '')}\". "
            f"Characters: Doraemon (blue robot cat) and Nobita (boy with glasses)."
        )

        url = (
            f"{self.gemini_api_base}/models/{self.image_model}"
            f":generateContent?key={self.api_key}"
        )

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
            },
        }

        client_kwargs: dict = {"timeout": httpx.Timeout(120.0)}
        if self.proxy:
            client_kwargs["proxy"] = self.proxy

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(**client_kwargs) as client:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                for candidate in data.get("candidates", []):
                    for part in candidate.get("content", {}).get("parts", []):
                        if "inlineData" in part:
                            return base64.b64decode(part["inlineData"]["data"])

                raise ValueError("No image data in response")

            except Exception as e:
                logger.warning(
                    "Image gen failed (story %d panel %d, attempt %d): %s",
                    story_index + 1, panel_index + 1, attempt + 1, e,
                )
                if attempt == 2:
                    raise
                await asyncio.sleep(2)

        raise RuntimeError("Image generation failed after 3 attempts")

    async def generate_all_images(
        self, script: dict, output_dir: Path
    ) -> list[list[str]]:
        """Generate all panel images, return list of file paths per story."""
        output_dir.mkdir(parents=True, exist_ok=True)
        semaphore = asyncio.Semaphore(self.max_concurrent)
        all_paths: list[list[str]] = []

        for si, story in enumerate(script.get("stories", [])):
            story_paths: list[str] = []
            tasks = []

            for pi, panel in enumerate(story.get("panels", [])):
                filename = f"panel-{si * 4 + pi + 1}.jpg"
                filepath = output_dir / filename

                async def gen(p=panel, s=si, i=pi, fp=filepath, fn=filename):
                    async with semaphore:
                        try:
                            img_bytes = await self.generate_panel_image(p, s, i)
                            fp.write_bytes(img_bytes)
                            logger.info("Generated %s", fn)
                            return fn
                        except Exception as e:
                            logger.error("Failed to generate %s: %s", fn, e)
                            return None

                tasks.append(gen())

            results = await asyncio.gather(*tasks)
            story_paths = [r for r in results if r is not None]
            all_paths.append(story_paths)

        return all_paths

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
