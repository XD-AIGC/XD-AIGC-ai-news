# Design Spec: Fashion Theme + Dynamic Subscription Analyzer

**Date:** 2026-04-21
**Project:** xd-aigc-ai-news
**Author:** Johnny (@zhongxingtian) + Claude
**Status:** Draft — awaiting user review

---

## 1. Problem & Goal

The current system is a single-theme AI news aggregator. We want to:

1. Add a second content theme (**fashion / 时尚潮流**) alongside the existing AI theme, so the system becomes an "AI + Fashion dual-theme aggregator".
2. Allow end-users to paste a URL and have the system analyze whether that URL can be subscribed to (technically feasible + content-relevant + quality-acceptable), then add it to the source pool on confirmation.
3. Keep the implementation **pragmatic and incremental** — no heavy refactor, no auth system (v1), no new framework.

### Non-goals (v1)

- User accounts / login / SSO — deferred to v2. v1 uses a shared global source pool with no per-user personalization.
- Per-user subscription feeds.
- Additional themes beyond ai/fashion.
- Real-time subscription health monitoring / alerting (only simple `last_fetch_status` tracking).
- New framework on frontend (stays vanilla JS).

---

## 2. Scope Summary

| Dimension | Decision |
|---|---|
| Theme structure | Two layers: `theme` (ai / fashion) → `focus_area` (name list) |
| AI focus_areas | Keep existing 6: 开源模型 / ComfyUI / 商用产品 / Agent & Skills / 3D生成与重建 / 训练与部署 |
| Fashion focus_areas | 3 new: 潮流 / 时装 / AI × 时尚 |
| Content language | Mixed Chinese + English |
| Chinese source access | Via existing **RSSHub** (小红书, 微博, B 站), no new scrapers |
| Multi-user | **Not in v1**. Shared global source pool. v2 will add auth. |
| Source storage | Static sources in `config.yaml`; dynamic (user-added) sources in new DB table `user_sources`; merged at pipeline startup |
| Subscription analyzer | LLM-assisted: URL → detect type → fetch sample → LLM analyze (theme + focus_area + quality verdict + reasoning) → user confirm → activate |
| Architecture approach | **In-place evolution** (no abstraction layer, no dual pipeline) |

---

## 3. Data Model

### 3.1 `ContentItem` (collectors/base.py)

Add a `Theme` enum and a `theme` field:

```python
class Theme(str, Enum):
    AI = "ai"
    FASHION = "fashion"

class ContentItem(BaseModel):
    # ... existing fields ...
    theme: Theme = Theme.AI   # default preserves legacy behavior
    # ai_categories naming kept as-is to avoid breaking compatibility
```

### 3.2 Database Schema Changes

**Modify `items` table:**

```sql
ALTER TABLE items ADD COLUMN theme TEXT NOT NULL DEFAULT 'ai';
CREATE INDEX idx_items_theme ON items(theme);
```

Old rows default to `'ai'` — matches reality, no backfill needed.

**New `user_sources` table** (combined subscription + analysis history):

```sql
CREATE TABLE user_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,                  -- original URL pasted by user
    url_hash TEXT NOT NULL UNIQUE,      -- sha1(normalize(url)) for idempotent lookup
    status TEXT NOT NULL,               -- 'pending' | 'active' | 'rejected' | 'disabled'
    source_type TEXT,                   -- 'rss' | 'youtube' | 'twitter' | 'bilibili' | ...
    normalized_config TEXT,             -- JSON: collector-specific config (feed_url, channel_id, etc.)
    theme TEXT,                         -- 'ai' | 'fashion' (LLM suggestion + user confirmation)
    focus_areas TEXT,                   -- JSON list of focus_area names (LLM suggestion, user may override on confirm)
    llm_reasoning TEXT,                 -- LLM's verdict explanation
    sample_json TEXT,                   -- up to 5 sampled items captured during analysis
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activated_at TIMESTAMP,
    last_fetch_at TIMESTAMP,
    last_fetch_status TEXT,             -- 'ok' | 'fail:<reason>'
    consecutive_failures INTEGER DEFAULT 0
);
CREATE INDEX idx_user_sources_status ON user_sources(status);
```

Single-table design (vs separate `subscribe_analyses`) — same URL dedupes naturally via `url_hash UNIQUE`, "my analyses" and "active subscriptions" are just `WHERE status = ?` queries. Upgrading to v2 multi-user only requires adding a `user_id` column.

### 3.3 Config Schema (`config.yaml`)

Replace flat `focus_areas` with nested `themes`:

```yaml
themes:
  ai:
    - name: "开源模型"
      keywords: [...existing keywords...]
    - name: "ComfyUI"
      keywords: [...]
    # keep existing 6
  fashion:
    - name: "潮流"
      keywords: ["streetwear", "街头", "sneakers", "球鞋", "Supreme", "Stussy",
                 "国潮", "Hypebeast", "Highsnobiety", "hype", "drop"]
    - name: "时装"
      keywords: ["runway", "时装周", "秀场", "haute couture", "Vogue", "LV",
                 "Prada", "Gucci", "BoF", "luxury", "designer", "collection"]
    - name: "AI × 时尚"
      keywords: ["AI fashion", "virtual model", "digital fashion", "AIGC 服装",
                 "AI 穿搭", "virtual try-on", "AI runway"]
```

**Backward compatibility shim**: config loader accepts both new (`themes`) and legacy (`focus_areas`) formats:

```python
def load_themes(config: dict) -> dict[str, list[dict]]:
    if "themes" in config:
        return config["themes"]
    if "focus_areas" in config:
        return {"ai": config["focus_areas"]}
    return {"ai": []}
```

Every source entry in `config.yaml` may carry an optional `theme` field (default `ai`):

```yaml
sources:
  rss:
    feeds:
      - { url: "https://openai.com/blog/rss.xml", name: "OpenAI Blog" }           # → ai (default)
      - { url: "https://hypebeast.com/feed", name: "Hypebeast", theme: "fashion" }
      - { url: "https://www.businessoffashion.com/rss", name: "BoF", theme: "fashion" }
  youtube:
    channels:
      - { id: "UCbfYPyITQ-7l4upoX8nvctg", name: "Two Minute Papers" }             # → ai (default)
      - { id: "<channel_id>", name: "<fashion channel>", theme: "fashion" }   # concrete fashion seed sources picked during implementation
```

**RSSHub route mapping** (new config section for user-submitted Chinese URLs):

```yaml
rsshub:
  base_url: "${RSSHUB_URL}"
  routes:
    - { pattern: "xiaohongshu\\.com/user/profile/(\\w+)", template: "/xiaohongshu/user/{1}" }
    - { pattern: "weibo\\.com/u/(\\d+)", template: "/weibo/user/{1}" }
    - { pattern: "space\\.bilibili\\.com/(\\d+)", template: "/bilibili/user/video/{1}" }
```

**LLM scoring prompts** (new per-theme prompt section):

```yaml
llm:
  # ... existing ...
  scoring_prompts:
    ai: |
      你是 AI 领域资深分析师。给下面内容打分（0-10）:
      - 技术突破性 / 开源价值 / 实用性 ...
    fashion: |
      你是时尚潮流趋势分析师。给下面内容打分（0-10）:
      - 趋势影响力 / 设计创新 / 话题热度 / 品牌动态重要性 ...
```

---

## 4. Pipeline Integration

### 4.1 Theme Assignment Principle

**Theme is declared by the source, inherited by items.** Not inferred from item content.

- Config-declared sources: each entry's `theme` field (default `ai`).
- User-submitted dynamic sources: LLM analysis sets theme, user confirms, stored in `user_sources.theme`.

Rationale: a feed's subject matter is stable (Hypebeast always publishes fashion). Inferring theme per-item causes edge-case mis-classification (e.g., "AI-generated sneakers" could match both themes).

### 4.2 Classifier Change (`processor/classifier.py`)

```python
def classify(item: ContentItem, themes_config: dict) -> list[str]:
    """Return focus_area names this item matches, scoped to its theme."""
    focus_areas = themes_config.get(item.theme.value, [])
    text = (item.title + " " + item.content).lower()
    matched = []
    for fa in focus_areas:
        if any(kw.lower() in text for kw in fa["keywords"]):
            matched.append(fa["name"])
    return matched
```

Keywords are matched only within the item's own theme. AI items will not be tagged with fashion focus_areas, and vice versa.

### 4.3 AIScorer Change (`processor/scorer.py`)

Scorer picks the prompt matching `item.theme` from `llm.scoring_prompts`. Fallback to `ai` prompt (with logged warning) if a theme's prompt is missing.

### 4.4 Pipeline Source Merge (`main.py`)

`build_collectors()` merges static and dynamic sources at startup:

```python
def build_collectors(config, db):
    static_sources = load_static_sources(config)                    # existing
    dynamic_sources = db.get_user_sources(status='active')          # new
    merged = merge_by_source_type(static_sources, dynamic_sources)  # new
    return instantiate_collectors(merged, ...)                      # existing, takes merged
```

Dynamic sources reuse existing collector classes — RSS, YouTube, Twitter, Bilibili, etc. No new collector class is introduced.

### 4.5 Dedup

No change. URL + title-similarity dedup is theme-agnostic and correct across themes (different URLs never false-merge).

---

## 5. Subscription Analyzer (new module)

### 5.1 Flow

```
User pastes URL
    → [1] Normalize URL + lookup user_sources by url_hash (cache)
    → [2] Detect source type (URL pattern → RSSHub route → direct RSS → HTML autodiscovery)
    → [3] Fetch sample (5-10 recent items, 10s timeout)
    → [4] LLM analyze (theme / focus_areas / quality 0-10 / verdict / reasoning)
    → [5] Persist to user_sources (status='pending')
    → [6] Return analysis JSON to frontend for user review
    → [7] User confirm/reject → /api/subscribe/confirm → status='active' | 'rejected'
    → Next pipeline run picks up active dynamic sources
```

### 5.2 URL Type Detector (`processor/subscribe_analyzer.py`)

Detection chain, ordered from most-specific to most-generic:

| Order | Detector | Match | Output |
|---|---|---|---|
| 1 | YouTube | `youtube.com/@handle` or `/channel/UC...` | `type=youtube, channel_id` |
| 2 | Bilibili | `space.bilibili.com/<uid>` | `type=bilibili, uid` |
| 3 | Twitter/X | `x.com/<user>` or `twitter.com/<user>` | `type=twitter, handle` |
| 4 | Reddit | `reddit.com/r/<sub>` | `type=reddit, sub` |
| 5 | Telegram | `t.me/<channel>` | `type=telegram, channel` |
| 6 | GitHub | `github.com/<owner>/<repo>` | `type=github, owner/repo` |
| 7 | RSSHub routes | pattern match from `config.rsshub.routes` | `type=rss, feed_url=<rsshub_url>` |
| 8 | Direct RSS | HTTP GET, content-type contains xml/atom/rss | `type=rss, feed_url=<original>` |
| 9 | HTML autodiscovery | parse `<link rel="alternate" type="application/rss+xml">` | `type=rss, feed_url=<discovered>` |
| 10 | Fallback | all detectors missed | `type=unknown` + friendly error |

Each detector is a pure function `detect(url) -> DetectionResult | None`. Main loop: `for detector in detectors: result = detector(url); if result: break`.

### 5.3 Sample Fetching

Reuse existing collector fetch methods, limited to N most recent items:

```python
async def fetch_sample(detection, n: int = 5) -> list[ContentItem]:
    if detection.type == "rss":
        return await sample_rss_feed(detection.feed_url, n)
    elif detection.type == "youtube":
        return await sample_youtube_channel(detection.channel_id, n)
    # ... etc per type
```

Timeout: 10 seconds. Failure → analysis returns `unreachable` error, no LLM call.

### 5.4 LLM Analysis

Prompt template (stored in `config.yaml.subscribe_analyzer.prompt`):

```
你是订阅分析助手。判断以下源是否值得订阅到"AI + 时尚"聚合系统。

可选主题与 focus_area：
- ai: [开源模型, ComfyUI, 商用产品, Agent & Skills, 3D生成与重建, 训练与部署]
- fashion: [潮流, 时装, AI × 时尚]

样本（最近 {n} 条）：
1. {title_1}
   {content_snippet_1}
...

请以 JSON 返回：
{
  "theme": "ai" | "fashion" | "neither",
  "suggested_focus_areas": ["..."],
  "quality_score": 0-10,
  "verdict": "accept" | "reject" | "manual_review",
  "reasoning": "2-3 句说明"
}

打分参考：
- 更新频率高、内容深度、原创性 → 加分
- 纯带货/营销、内容低质、与两个主题都无关 → 减分
- verdict: >=6 accept, <4 reject, 4-5.9 manual_review
```

LLM failure handling: JSON parse failure → retry once → if still failing, return `verdict=manual_review` with `reasoning="LLM 分析失败，请人工判断"`. **Do not block the user** — they can still look at the sample and decide manually.

### 5.5 API Surface (`web/routers/subscribe.py`, new)

```
POST   /api/subscribe/analyze
  body: { "url": "..." }
  response: {
    "analysis_id": 42,
    "url_hash": "...",
    "detected_type": "rss" | ...,
    "sample": [{title, url, published_at, snippet}, ...],
    "llm": { "theme", "suggested_focus_areas", "quality_score", "verdict", "reasoning" },
    "cached": bool,
    "already_subscribed": bool,
    "previously_rejected": bool
  }

POST   /api/subscribe/confirm
  body: {
    "analysis_id": 42,
    "action": "accept" | "reject",
    "overrides": { "theme", "focus_areas", "name" }   # optional user edits
  }
  response: { "status": "active" | "rejected", "source_id": 42 }

GET    /api/subscribe/list?status=active|pending|rejected|disabled
DELETE /api/subscribe/:id
PATCH  /api/subscribe/:id   # toggle enable/disable, edit focus_areas
```

### 5.6 Caching & Deduplication

- URL normalization: strip fragment, lowercase host, remove tracking params. `url_hash = sha1(normalized_url)`.
- Lookup `user_sources.url_hash` before any fetch/LLM call.
- Cached responses include flags: `already_subscribed`, `previously_rejected`, `cached` (pending from earlier analysis).
- Re-analysis of a `rejected` URL requires explicit user action (frontend shows "you rejected this before — re-analyze?" button).

---

## 6. Frontend UI

### 6.1 Layout Changes (`web/static/index.html`)

```
┌─ Header ────────────────────────────────────────────────┐
│ AI资讯聚合                       [+ 添加订阅] [订阅管理] │
│                                                          │
│   [🤖 AI]  [👗 时尚]   ← theme tab                       │
│                                                          │
│   focus_area filter: [全部] [开源模型] [ComfyUI] ...     │
├─ Content Grid ─────────────────────────────────────────┤
│   ... item cards (filtered by theme + focus_area) ...    │
└──────────────────────────────────────────────────────────┘
```

- Active theme persisted in `localStorage`.
- Switching theme re-fetches items with `?theme=` query param and replaces the focus_area filter chips with that theme's set.

### 6.2 Subscribe Analyzer Modal (`web/static/subscribe-modal.js`, new)

Triggered by `[+ 添加订阅]` button. Uses native `<dialog>` element — no framework.

States:
1. **Input**: URL input field + "分析" button
2. **Loading**: spinner while analyze API runs (expect 5-15s: fetch + LLM)
3. **Result**: shows detected type, sample preview (top 5 items), LLM verdict + reasoning, editable theme dropdown, editable focus_area multi-select, editable source name
4. **Action**: [确认订阅] [拒绝] [取消]

Special cases:
- `already_subscribed=true` → show "此源已在你的订阅列表中" + "去查看" button
- `previously_rejected=true` → show "你之前拒绝过此源" + "重新分析" button
- `verdict=reject` → primary button styled as "拒绝" (destructive), not "确认"
- `verdict=manual_review` → no pre-selected primary button, user picks

### 6.3 Subscription Management Page (`web/static/subscribe.html`, new)

Table view with tabs for status filter (全部 / 活跃 / 待处理 / 已拒绝 / 已禁用). Rows show: name, type icon, theme badge, focus_areas chips, last fetch time + status. Per-row actions: 查看样本 / 禁用 / 启用 / 删除 (action set depends on current status).

**Only manages dynamic sources** (DB). Static sources in `config.yaml` are not exposed to the UI — editing yaml is an admin action.

### 6.4 Files Changed / Added

- `web/static/index.html` — add theme tabs + "+ 添加订阅" / "订阅管理" buttons
- `web/static/subscribe.html` — new subscription management page
- `web/static/subscribe-modal.js` — new modal logic
- `web/static/app.js` — theme switching, API calls include `?theme=`
- `web/static/style.css` — new tab, modal, badge styles

**No frontend framework introduced.** Vanilla JS + native `<dialog>`.

### 6.5 Backend API Changes

- `GET /api/items` gains `theme` query parameter for filtering.
- New router `web/routers/subscribe.py` with endpoints from §5.5.

---

## 7. Migration & Rollout

### 7.1 Migration Script

`scripts/migrate_v2.sql` — run manually once per environment:

```sql
-- Add theme column to items (default 'ai' keeps legacy data correct)
ALTER TABLE items ADD COLUMN theme TEXT NOT NULL DEFAULT 'ai';
CREATE INDEX idx_items_theme ON items(theme);

-- Create user_sources table
CREATE TABLE user_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    url_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    source_type TEXT,
    normalized_config TEXT,
    theme TEXT,
    focus_areas TEXT,
    llm_reasoning TEXT,
    sample_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    activated_at TIMESTAMP,
    last_fetch_at TIMESTAMP,
    last_fetch_status TEXT,
    consecutive_failures INTEGER DEFAULT 0
);
CREATE INDEX idx_user_sources_status ON user_sources(status);
```

Run: `sqlite3 data/news.db < scripts/migrate_v2.sql`

No Alembic introduced. The project has no migration tooling today; a single SQL file keeps it simple.

### 7.2 Config Migration

Zero operation. The loader shim reads both old `focus_areas` and new `themes`. Legacy `config.yaml` files run unchanged. Admins may migrate to the new format at their convenience.

### 7.3 Rollback

Frontend: `git revert web/` — theme tabs disappear, backend remains compatible.

Backend: `git revert` all code changes. DB schema changes are additive (added column has a default, added table unused by old code) — safe to leave in place.

**No down migration is needed.** Schema-only additions do not break old code paths.

---

## 8. Error Handling Matrix

| Scenario | Behavior | User-visible |
|---|---|---|
| Analyze: URL 404 / timeout | `detected_type='unknown'`, not saved | "无法访问此 URL，请检查网络或 URL 是否正确" |
| Analyze: RSS parse failure | Same as above | "不是有效 RSS，也未在页面上找到订阅链接" |
| Analyze: LLM returns non-JSON | Retry once; on second failure → `manual_review` | "AI 分析暂时不可用，请根据样本内容自行判断" |
| Analyze: URL already active | Skip LLM, return cached row | "此源已在订阅中" + 跳转 |
| Analyze: URL previously rejected | Return cached row with flag | "你之前拒绝过此源 [重新分析]" |
| Pipeline fetch fails for dynamic source | Record `last_fetch_status='fail:<reason>'`, increment `consecutive_failures`, continue | Management page shows ✗ with reason |
| Pipeline: `consecutive_failures >= 5` | Auto-set `status='disabled'`, log warning | Management page shows "已自动禁用 [重新启用]" |
| Classifier: unknown theme on item | Log warning, fallback to `ai` focus_areas | Invisible (log only) |
| Scorer: no prompt for theme | Fallback to `ai` prompt, log warning | Invisible (log only) |

---

## 9. Testing Strategy

Project has **no existing test suite** (per `CLAUDE.md`). We do not introduce a sweeping testing overhaul. Only high-risk new modules get targeted tests.

### P0 (must test)

1. **URL detector** (`processor/subscribe_analyzer.py`) — pure function, many branches, easiest to break silently.
   - Cases: each URL pattern (youtube/bilibili/twitter/reddit/telegram/github/rsshub/direct-rss/html-autodiscover/unknown)
   - Edge: query string, fragment, http vs https, `www.` prefix, case sensitivity
   - ~30 test cases, no mocking needed
2. **Config loader shim** — guarantee both old and new formats load.
   - 3 cases: new `themes`, legacy `focus_areas`, both absent
3. **Classifier theme-scoping** — ensure AI items don't pick up fashion focus_areas and vice versa.
   - 4 cases: ai-item with ai-keywords / ai-item with fashion-keywords (no match) / fashion-item with fashion-keywords / cross-theme keywords

### P1 (should test)

4. **Analyzer end-to-end** with mocked LLM + HTTP
   - Happy path: RSS URL → detect → sample → mock LLM JSON → correct response
   - LLM non-JSON fallback

### P2 (manual verification only)

- Frontend UI (small surface, eyeball it)
- Real RSSHub connectivity (deployment concern, not a code concern)

### Test Infrastructure

- New directory `tests/`, using `pytest` + `pytest-asyncio`
- Add to `requirements-dev.txt`: `pytest`, `pytest-asyncio`, `pytest-cov`
- Invocation: `pytest tests/`
- No CI integration introduced (project has none today)

---

## 10. Observability (v1 minimal)

- All LLM calls logged via existing logger: `url_hash + token count + verdict + elapsed_ms`
- `user_sources.last_fetch_status` + `consecutive_failures` visible in management page
- New endpoint `GET /api/subscribe/stats` returning: `{active_count, pending_count, rejected_count, analyses_last_24h}`
- No Prometheus / Grafana / alerting

---

## 11. Deployment

- systemd timer for daily pipeline run — unchanged
- FastAPI `web` module auto-serves new `/api/subscribe/*` routes — no config change
- **One-time manual step per environment**: run `sqlite3 data/news.db < scripts/migrate_v2.sql`
- Dependencies additions: none runtime; dev-only `pytest*` for tests

---

## 12. Files Changed / Added

### Changed
- `collectors/base.py` — add `Theme` enum, `theme` field on `ContentItem`
- `config.yaml` — nested `themes`, per-source `theme` field, `rsshub.routes`, `llm.scoring_prompts`, `subscribe_analyzer.prompt`
- `processor/classifier.py` — theme-scoped keyword matching
- `processor/scorer.py` — per-theme scoring prompt selection
- `main.py` — merge static + dynamic sources in `build_collectors()`
- `web/app.py` — mount new subscribe router
- `storage/` — config loader shim; add `user_sources` CRUD
- `web/static/index.html`, `app.js`, `style.css` — theme tabs, add-subscribe button, theme-filtered API calls

### Added
- `processor/subscribe_analyzer.py` — URL detector chain + sample fetch + LLM analyze
- `web/routers/subscribe.py` — subscribe API endpoints
- `storage/user_sources.py` — `user_sources` table CRUD
- `web/static/subscribe.html`, `subscribe-modal.js` — frontend
- `scripts/migrate_v2.sql` — one-time DB migration
- `tests/` — test suite (P0 + P1)
- `requirements-dev.txt` — pytest dependencies

---

## 13. Deferred to v2

- User accounts + auth (SSO / email-password / lightweight username)
- Per-user subscription lists and per-user home feeds
- Source health dashboard (beyond last_fetch_status)
- Alembic-based migration tooling
- Additional themes (e.g., gaming, design) — theme abstraction can be introduced when needed
- CI integration

---

## 14. Open Questions

None remaining after brainstorming. All questions resolved:

- Theme architecture: two-layer (theme → focus_area) ✓
- Fashion focus_areas: 潮流 / 时装 / AI × 时尚 ✓
- Subscription analysis depth: LLM-assisted (option C) ✓
- Multi-user scope: deferred to v2 ✓
- Source storage model: shared global pool ✓
- Chinese source access: via RSSHub, no new scrapers ✓
- Dynamic source persistence: single `user_sources` table ✓
