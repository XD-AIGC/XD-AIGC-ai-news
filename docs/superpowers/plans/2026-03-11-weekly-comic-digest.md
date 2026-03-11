# Weekly Comic Digest Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-generate a weekly Doraemon-style manga comic digest of AI news, published to GitHub Pages every Sunday night.

**Architecture:** A new `processor/comic_generator.py` handles LLM scriptwriting and Nano Banana Pro image generation. A new `processor/weekly_digest.py` orchestrates the weekly pipeline: query DB for the week's top items, call the comic generator, and output to GitHub Pages. The frontend is a new `docs/weekly.html` + `docs/weekly.js` that renders the digest from static JSON.

**Tech Stack:** Python 3.10+, httpx (Gemini native API for image gen), existing LLM via OpenAI-compatible API, static HTML/CSS/JS for GitHub Pages.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `storage/database.py` | Modify | Add `get_items_by_date_range()` method |
| `processor/comic_generator.py` | Create | LLM script writing + Nano Banana Pro image generation |
| `processor/weekly_digest.py` | Create | Orchestrate weekly pipeline, aggregate data, call comic generator, write output |
| `outputs/github_pages_writer.py` | Modify | Add `write_weekly()` method for weekly JSON + images |
| `docs/weekly.html` | Create | Static weekly digest page (Morandi color scheme) |
| `docs/weekly.js` | Create | Client-side rendering of weekly digest from JSON |
| `docs/index.html` | Modify | Add nav tab linking to weekly page |
| `main.py` | Modify | Add `--weekly` CLI flag |
| `config.yaml` | Modify | Add `weekly:` config section |
| `deploy/ai-news-weekly.timer` | Create | Systemd timer: Sunday 22:00 |
| `deploy/ai-news-weekly.service` | Create | Systemd service for weekly run |

---

## Chunk 1: Database + Comic Generator Backend

### Task 1: Add date range query to database

**Files:**
- Modify: `storage/database.py`

- [ ] **Step 1: Add `get_items_by_date_range` method**

Add after `get_items_by_date` (line ~104) in `storage/database.py`:

```python
def get_items_by_date_range(
    self, start_date: str, end_date: str, min_score: float | None = None
) -> list[ContentItem]:
    """Get items collected between start_date and end_date (inclusive, YYYY-MM-DD)."""
    query = "SELECT * FROM news WHERE collected_at >= ? AND collected_at < ?"
    params: list = [f"{start_date}T00:00:00", f"{end_date}T23:59:59"]

    if min_score is not None:
        query += " AND ai_score >= ?"
        params.append(min_score)

    query += " ORDER BY ai_score DESC NULLS LAST, collected_at DESC"

    cursor = self._conn.cursor()
    cursor.execute(query, params)
    return [self._row_to_item(row) for row in cursor.fetchall()]
```

- [ ] **Step 2: Verify manually**

Run: `python -c "from storage.database import NewsDatabase; db = NewsDatabase(); db.connect(); print(len(db.get_items_by_date_range('2026-03-01', '2026-03-11'))); db.close()"`

- [ ] **Step 3: Commit**

```bash
git add storage/database.py
git commit -m "feat: add get_items_by_date_range to NewsDatabase"
```

### Task 2: Create comic generator — LLM scriptwriter

**Files:**
- Create: `processor/comic_generator.py`

- [ ] **Step 1: Create file with LLM scriptwriter**

Create `processor/comic_generator.py` with the script-writing portion. The class takes LLM config and generates a comic script JSON from a list of top news items.

```python
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
```

- [ ] **Step 2: Verify import**

Run: `python -c "from processor.comic_generator import ComicGenerator; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add processor/comic_generator.py
git commit -m "feat: add comic generator with LLM scriptwriter and image gen"
```

### Task 3: Create weekly digest orchestrator

**Files:**
- Create: `processor/weekly_digest.py`

- [ ] **Step 1: Create weekly digest orchestrator**

```python
"""Weekly digest: aggregate data, generate comics, output to GitHub Pages."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collectors.base import ContentItem
from processor.comic_generator import ComicGenerator
from storage.database import NewsDatabase

logger = logging.getLogger(__name__)


def get_week_range(ref_date: datetime | None = None) -> tuple[str, str, str]:
    """Get the ISO week number and date range for the previous week.

    Returns: (week_label like '2026-W11', start_date, end_date) as YYYY-MM-DD.
    """
    if ref_date is None:
        ref_date = datetime.now(timezone.utc)

    # Go back to last Monday
    days_since_monday = ref_date.weekday()
    last_monday = ref_date - timedelta(days=days_since_monday + 7)
    last_sunday = last_monday + timedelta(days=6)

    iso_year, iso_week, _ = last_monday.isocalendar()
    week_label = f"{iso_year}-W{iso_week:02d}"
    start_date = last_monday.strftime("%Y-%m-%d")
    end_date = last_sunday.strftime("%Y-%m-%d")

    return week_label, start_date, end_date


async def generate_weekly_digest(
    db: NewsDatabase,
    comic_gen: ComicGenerator,
    output_dir: str = "./docs",
) -> dict | None:
    """Main weekly pipeline: query DB, generate comics, write output."""
    week_label, start_date, end_date = get_week_range()
    logger.info(
        "Weekly digest: %s (%s to %s)", week_label, start_date, end_date
    )

    # Get all items for the week
    all_items = db.get_items_by_date_range(start_date, end_date)
    if not all_items:
        logger.warning("No items found for %s, skipping weekly digest", week_label)
        return None

    # Get scored items sorted by score
    scored = [i for i in all_items if i.ai_score is not None]
    scored.sort(key=lambda x: x.ai_score or 0, reverse=True)
    top10 = scored[:10]

    if len(top10) < 3:
        logger.warning("Only %d scored items for %s, need at least 3", len(top10), week_label)
        return None

    # Count unique sources
    sources = {i.source_type.value for i in all_items}

    logger.info(
        "Weekly data: %d total items, %d scored, %d sources",
        len(all_items), len(scored), len(sources),
    )

    # Step 1: Generate script
    logger.info("Generating comic script...")
    script = await comic_gen.generate_script(top10, len(all_items), len(sources))
    logger.info("Script generated: %s", script.get("week_title", ""))

    # Step 2: Generate images
    week_dir = Path(output_dir) / "data" / "weekly" / week_label
    logger.info("Generating %d panel images...", sum(
        len(s.get("panels", [])) for s in script.get("stories", [])
    ))
    panel_paths = await comic_gen.generate_all_images(script, week_dir)

    # Step 3: Attach panel paths to script
    for si, story in enumerate(script.get("stories", [])):
        if si < len(panel_paths):
            story["panels_images"] = panel_paths[si]

    # Step 4: Build digest JSON
    # Category stats
    cat_counts: dict[str, int] = {}
    for item in all_items:
        for cat in item.ai_categories or []:
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

    digest = {
        "week": week_label,
        "date_range": f"{start_date} — {end_date}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_news": len(all_items),
        "total_sources": len(sources),
        "week_title": script.get("week_title", f"第{week_label}周报"),
        "editor_note": script.get("editor_note", ""),
        "stories": script.get("stories", []),
        "top10": [
            {"rank": i + 1, "title": item.title, "score": item.ai_score,
             "categories": item.ai_categories}
            for i, item in enumerate(top10)
        ],
        "stats": {
            "by_category": cat_counts,
            "by_source": {s: sum(1 for i in all_items if i.source_type.value == s) for s in sources},
        },
    }

    # Step 5: Write digest JSON
    digest_file = week_dir / "digest.json"
    import json
    digest_file.write_text(
        json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Step 6: Update weekly index
    _update_weekly_index(Path(output_dir) / "data" / "weekly", week_label, digest)

    logger.info("Weekly digest complete: %s (%d stories, %d panels)",
                week_label, len(digest["stories"]),
                sum(len(s.get("panels_images", [])) for s in digest["stories"]))

    return digest


def _update_weekly_index(weekly_dir: Path, week_label: str, digest: dict) -> None:
    """Update weekly/index.json with the new week entry."""
    import json

    index_file = weekly_dir / "index.json"
    weeks: list[dict] = []
    if index_file.exists():
        try:
            weeks = json.loads(index_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            weeks = []

    # Update or add
    existing = {w["week"]: w for w in weeks}
    existing[week_label] = {
        "week": week_label,
        "title": digest.get("week_title", ""),
        "date_range": digest.get("date_range", ""),
        "story_count": len(digest.get("stories", [])),
    }
    weeks = sorted(existing.values(), key=lambda w: w["week"], reverse=True)

    weekly_dir.mkdir(parents=True, exist_ok=True)
    index_file.write_text(
        json.dumps(weeks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
```

- [ ] **Step 2: Verify import**

Run: `python -c "from processor.weekly_digest import get_week_range; print(get_week_range())"`

- [ ] **Step 3: Commit**

```bash
git add processor/weekly_digest.py
git commit -m "feat: add weekly digest orchestrator"
```

### Task 4: Wire up main.py with --weekly flag

**Files:**
- Modify: `main.py`
- Modify: `config.yaml`

- [ ] **Step 1: Add weekly config to config.yaml**

Add after the `output:` section (before `proxy:`):

```yaml
weekly:
  enabled: true
  image_model: "nano-banana-pro-preview"
  story_count: 3
  panels_per_story: 4
  max_concurrent_images: 3
```

- [ ] **Step 2: Add --weekly arg and run_weekly function to main.py**

Add import at top:
```python
from processor.weekly_digest import generate_weekly_digest
from processor.comic_generator import ComicGenerator
```

Add after `backfill_notion` function:
```python
async def run_weekly(args: argparse.Namespace) -> None:
    """Generate weekly comic digest."""
    load_dotenv()
    config = load_config(args.config)

    proxy_cfg = config.get("proxy", {})
    proxy_url = proxy_cfg.get("http")

    db = NewsDatabase(config.get("database", {}).get("path", "./data/news.db"))
    db.connect()

    try:
        llm_cfg = config.get("llm", {})
        weekly_cfg = config.get("weekly", {})
        ghpages_cfg = config.get("output", {}).get("github_pages", {})
        output_dir = ghpages_cfg.get("output_dir", "./docs")

        comic_config = {
            "llm_model": llm_cfg.get("model", "gemini-2.5-flash"),
            "image_model": weekly_cfg.get("image_model", "nano-banana-pro-preview"),
            "api_key": llm_cfg.get("api_key", ""),
            "base_url": llm_cfg.get("base_url", ""),
            "proxy": proxy_url if not args.no_proxy else None,
            "max_concurrent_images": weekly_cfg.get("max_concurrent_images", 3),
        }

        comic_gen = ComicGenerator(comic_config)
        digest = await generate_weekly_digest(db, comic_gen, output_dir)

        if digest:
            logger.info("Weekly digest generated: %s", digest["week"])
        else:
            logger.warning("Weekly digest skipped (no data)")
    finally:
        db.close()
```

Add CLI argument in `main()` after `--serve`:
```python
parser.add_argument(
    "--weekly",
    action="store_true",
    help="Generate weekly comic digest",
)
```

Add handler in `main()` before `elif args.backfill_notion:`:
```python
elif args.weekly:
    asyncio.run(run_weekly(args))
```

- [ ] **Step 3: Verify**

Run: `python main.py --help` and check `--weekly` appears.

- [ ] **Step 4: Commit**

```bash
git add main.py config.yaml
git commit -m "feat: add --weekly CLI flag and config for comic digest"
```

---

## Chunk 2: Frontend (weekly.html + weekly.js)

### Task 5: Create weekly.html page

**Files:**
- Create: `docs/weekly.html`

- [ ] **Step 1: Create the Morandi-themed weekly page**

Create `docs/weekly.html` — a standalone HTML page that loads `weekly.js` and renders the digest. Uses the design from our mockup v10: 1380px centered, Morandi colors, left-comic right-text layout. The page reads from `data/weekly/index.json` to list weeks, then loads `data/weekly/YYYY-WNN/digest.json` for the selected week.

Key design tokens to embed in CSS:
- `--bg: #e8e0d8`, `--card: #f5f0eb`, `--panel-bg: #ddd5cb`, `--panel-border: #5a5249`
- `--text-primary: #4a4039`, `--text-secondary: #6b5f54`, `--accent: #a3907a`
- `--score: #c4a882`, `--trend-up: #8a9e8b`
- Story label colors: `#c4a882` (headline), `#8a9e8b` (trends), `#c9a87e` (comedy)
- Title: 28px/800, body: 16px/2.0 line-height, banner: 36px, section: 22px

- [ ] **Step 2: Verify file created**

Open `docs/weekly.html` in browser, should show loading state.

- [ ] **Step 3: Commit**

```bash
git add docs/weekly.html
git commit -m "feat: add weekly digest page with Morandi theme"
```

### Task 6: Create weekly.js client-side renderer

**Files:**
- Create: `docs/weekly.js`

- [ ] **Step 1: Create the JS renderer**

`docs/weekly.js` handles:
- Load `data/weekly/index.json` on page load
- Render week selector (← prev | current | next →)
- On week select, fetch `data/weekly/{week}/digest.json`
- Render banner (week_title, date_range, total_news, tags from top10 categories)
- Render 3 stories: left side = 2×2 comic grid (images from panel paths), right side = stacked cards (title, summary, highlights, community_quotes/jokes, related_news, doraemon_quote)
- Render bottom row: top10 list + stats + editor_note
- Mobile responsive: below 768px switch to vertical layout

- [ ] **Step 2: Commit**

```bash
git add docs/weekly.js
git commit -m "feat: add weekly.js client-side digest renderer"
```

### Task 7: Add navigation tab to daily page

**Files:**
- Modify: `docs/index.html`

- [ ] **Step 1: Add tab navigation**

Add a nav bar at the top of `docs/index.html` with two links: "日报" (active, current page) and "周报" (links to `weekly.html`). Same Morandi-styled nav bar should be added to `weekly.html` with "周报" active.

- [ ] **Step 2: Commit**

```bash
git add docs/index.html docs/weekly.html
git commit -m "feat: add nav tabs between daily and weekly pages"
```

---

## Chunk 3: Deployment + gitignore

### Task 8: Systemd timer and service

**Files:**
- Create: `deploy/ai-news-weekly.timer`
- Create: `deploy/ai-news-weekly.service`

- [ ] **Step 1: Create weekly timer**

`deploy/ai-news-weekly.timer`:
```ini
[Unit]
Description=AI News Weekly Digest - run Sunday at 22:00 CST

[Timer]
OnCalendar=Sun *-*-* 22:00:00
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
```

- [ ] **Step 2: Create weekly service**

`deploy/ai-news-weekly.service`:
```ini
[Unit]
Description=AI News Weekly Comic Digest
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/AIGC_Group/XD-AIGC-ai-news
ExecStart=/AIGC_Group/miniconda3/envs/xd-aigc-ainews/bin/python main.py --weekly
ExecStartPost=/bin/bash -c 'cd /AIGC_Group/XD-AIGC-ai-news && git add docs/data/weekly/ && git diff --cached --quiet || git commit -m "chore: update weekly digest" && git push'
TimeoutStartSec=600
Environment="PATH=/AIGC_Group/miniconda3/envs/xd-aigc-ainews/bin:/usr/local/bin:/usr/bin:/bin"
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: Commit**

```bash
git add deploy/ai-news-weekly.timer deploy/ai-news-weekly.service
git commit -m "feat: add systemd timer for weekly digest (Sunday 22:00)"
```

### Task 9: Update .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add weekly data exception**

Add after `!docs/data/`:
```
!docs/data/weekly/
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: allow docs/data/weekly/ in git"
```

### Task 10: Test full pipeline

- [ ] **Step 1: Run weekly digest locally**

```bash
python main.py --weekly --no-proxy -v
```

Check:
- `docs/data/weekly/` directory created with week folder
- `digest.json` contains 3 stories with panel image paths
- 12 panel images generated (`.jpg` files)
- `index.json` updated

- [ ] **Step 2: Open weekly.html in browser**

Verify the page renders correctly with comics and text.

- [ ] **Step 3: Final commit and push**

```bash
git add docs/data/weekly/
git commit -m "feat: first weekly comic digest"
git push
```
