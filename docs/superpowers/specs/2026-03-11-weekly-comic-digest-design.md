# Weekly Comic Digest — Design Spec

## Overview

Auto-generated weekly AI news digest presented as a Doraemon-style manga comic on GitHub Pages. Runs every Sunday night, producing 3 stories × 4 panels of comics with AI-written scripts and Nano Banana Pro-generated artwork.

## Characters

- **Doraemon** (哆啦A梦): The knowledgeable AI expert, explains news and tech
- **Nobita** (大雄): The curious but lazy everyman, asks questions and reacts

## Story Structure

Each weekly digest contains **3 stories**, each **4 panels**:

| Story | Theme | Tone | Content |
|-------|-------|------|---------|
| Story 1 | Top headline of the week | Informative, exciting | Biggest news event, community reaction |
| Story 2 | Domain trends (open source, tools, etc.) | Educational, comparative | Multiple related events grouped together |
| Story 3 | Comedy / roast | Humorous, satirical | Nobita's AI struggles, industry absurdities, Doraemon's witty comebacks |

## Pipeline

```
Weekly Top 10 (from SQLite, 7 days of high-scored items)
  │
  ├─ Step 1: LLM Scriptwriter
  │   Input: Top 10 titles + summaries + scores + categories
  │   Output: JSON with 3 stories, each containing:
  │     - story_title: string
  │     - story_theme: "headline" | "trends" | "comedy"
  │     - story_summary: string (200 chars, for right panel text)
  │     - highlights: list[string] (key points)
  │     - community_quotes: list[string] (for story 1/2)
  │     - jokes: list[string] (for story 3)
  │     - related_news: list[{title, score}]
  │     - panels: list[4] of {scene_description, dialogue_cn, dialogue_jp_sfx}
  │     - doraemon_quote: string (weekly summary quote)
  │
  ├─ Step 2: LLM Prompt Writer
  │   Input: Panel descriptions from Step 1
  │   Output: 12 English prompts for Nano Banana Pro
  │   Each prompt: "4-panel manga, Doraemon style, black and white,
  │     panel N of 4: [scene]. Character says '[dialogue]'.
  │     Japanese sound effects. Speech bubbles with Chinese text."
  │
  ├─ Step 3: Nano Banana Pro Image Generation
  │   Model: nano-banana-pro-preview (Google Generative AI API)
  │   Auth: OPENAI_API_KEY (Google AI Studio key)
  │   Endpoint: generativelanguage.googleapis.com/v1beta
  │   Concurrency: 3 parallel requests (rate limit safe)
  │   Output: 12 JPEG images (~1MB each)
  │   Retry: up to 2 retries per image on failure
  │
  └─ Step 4: Output
      - Save images to docs/data/weekly/YYYY-WNN/panel-{1-12}.jpg
      - Generate docs/data/weekly/YYYY-WNN/digest.json (metadata)
      - Update docs/data/weekly/index.json (week list)
      - Commit + push via systemd ExecStartPost
```

## Data Schema

### digest.json
```json
{
  "week": "2026-W11",
  "date_range": "2026-03-03 — 2026-03-09",
  "generated_at": "2026-03-09T22:30:00Z",
  "total_news": 1247,
  "total_sources": 12,
  "vs_last_week": { "news_pct": 23, "avg_score_delta": 0.3 },
  "editor_note": "本周是 2026 最疯狂的一周...",
  "stories": [
    {
      "title": "GPT-5 来了！AI 进入新纪元",
      "theme": "headline",
      "label": "本周头条",
      "label_color": "#c4a882",
      "summary": "OpenAI 本周发布 GPT-5...",
      "date": "2026-03-05",
      "category": "商用产品",
      "highlights": ["代码 +47%", "视频流分析", "成本 -60%", "原生 Agent"],
      "community_quotes": [
        {"text": "这不是渐进升级，这是代际飞跃", "author": "@karpathy"},
        {"text": "终于不用 Stack Overflow 了", "source": "Reddit"}
      ],
      "related_news": [
        {"title": "GPT-5 发布", "score": 9.8},
        {"title": "Sam Altman 专访", "score": 8.5}
      ],
      "panels": ["panel-1.jpg", "panel-2.jpg", "panel-3.jpg", "panel-4.jpg"]
    }
  ],
  "top10": [
    {"rank": 1, "title": "GPT-5 正式发布", "score": 9.8},
    ...
  ],
  "stats": {
    "by_category": {"开源模型": 35, "商用产品": 25, ...},
    "by_source": {"rss": 120, "twitter": 80, ...}
  }
}
```

### weekly/index.json
```json
[
  {"week": "2026-W11", "title": "AI 圈又炸了", "date_range": "3.3—3.9", "story_count": 3},
  {"week": "2026-W10", "title": "...", "date_range": "2.24—3.2", "story_count": 3}
]
```

## Page Design

### Layout: 1380px centered, Morandi color palette

**Color Scheme:**
- Background: `#e8e0d8` (warm gray)
- Cards: `#f5f0eb` (cream white)
- Comic panels: `#ddd5cb` (light taupe)
- Comic border: `#5a5249` (dark brown)
- Text primary: `#4a4039` (deep brown)
- Text secondary: `#6b5f54` (medium brown)
- Accent: `#a3907a` (taupe), `#c4a882` (camel)
- Story 1 label: `#c4a882` (camel)
- Story 2 label: `#8a9e8b` (sage green)
- Story 3 label: `#c9a87e` (warm gold)
- Score color: `#c4a882`
- Trend up: `#8a9e8b`

**Typography:**
- Banner title: 36px, weight 800
- Story title: 28px, weight 800
- Body text: 16px, line-height 2.0
- Card labels: 16px, weight 600
- Section titles (bottom): 22px, weight 700
- Stats numbers: 28px, weight 800
- Doraemon quote: 18px, italic

**Structure (top to bottom, scrollable):**

1. **Top nav bar** — title + week selector (← W10 | W11 | W12 →)
2. **Banner** — week title (36px) + date range + total count + hashtag pills
3. **Story 1** — left: 4-panel comic (flex 1.6) | right: title card + highlights + community + related news (flex 1)
4. **Story 2** — same layout, different label color
5. **Story 3** — same layout, comedy content (jokes, Doraemon quote, meme moments)
6. **Bottom row** — 3 cards: Top 10 list (flex 1.2) + Stats (flex 0.4) + Editor note (flex 0.5)

**Mobile responsive:** Below 768px, switch to vertical layout (comic on top, text below).

## New Files

| File | Purpose | Lines (est.) |
|------|---------|-------------|
| `processor/comic_generator.py` | LLM scriptwriter + Nano Banana Pro image gen | ~300 |
| `processor/weekly_digest.py` | Aggregate weekly data, orchestrate pipeline | ~150 |
| `outputs/github_pages_writer.py` | Extend: write weekly JSON + images | ~50 added |
| `docs/weekly.html` | Static weekly digest page | ~100 |
| `docs/weekly.js` | Client-side rendering from digest.json | ~200 |
| `deploy/ai-news-weekly.timer` | Systemd timer: Sunday 22:00 | ~10 |
| `deploy/ai-news-weekly.service` | Systemd service for weekly run | ~15 |

## Modified Files

| File | Change |
|------|--------|
| `main.py` | Add `--weekly` CLI flag, call weekly pipeline |
| `config.yaml` | Add `weekly:` section (enabled, model, story_count) |
| `docs/index.html` | Add nav tab: 日报 \| 周报 |
| `.gitignore` | Ensure `docs/data/weekly/` is not ignored |

## Config Addition

```yaml
weekly:
  enabled: true
  image_model: "nano-banana-pro-preview"
  story_count: 3
  panels_per_story: 4
  schedule: "sunday"
  characters:
    - name: "Doraemon"
      role: "AI expert, explains news"
    - name: "Nobita"
      role: "curious everyman, reacts and asks questions"
```

## Cost Estimate

| Item | Per Week |
|------|----------|
| LLM scriptwriter (2 calls, ~3K tokens) | ~$0.01 |
| 12 image generations (Nano Banana Pro) | ~$0.48 |
| **Total** | **~$0.50/week** |

## Error Handling

- Image generation failure: retry 2x, skip panel on 3rd failure, use placeholder
- LLM script failure: fall back to simple template (title-only panels)
- No data for week: skip weekly generation, log warning

## Future: Monthly Digest

Monthly digest will reuse the same infrastructure:
- Aggregate 4 weekly digests
- LLM summarizes the month's themes from weekly scripts
- Generate 2-3 stories covering the month
- Separate `docs/monthly.html` page
- Triggered on 1st of each month
