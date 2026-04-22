# v2 Backlog

Parking lot for follow-up items surfaced during v1 (Fashion Theme + Subscription Analyzer) development and deployment. Each item should eventually get its own spec + plan before implementation.

Items are tagged by priority:
- **🔴 High** — noticeable impact on UX / reliability / cost
- **🟡 Medium** — cleanup / optimization / ergonomics
- **🟢 Low** — nice-to-haves, polish

---

## Architecture & Code Quality

### ✅ Unify three `load_config` implementations (DONE 2026-04-22)
Single `load_config(path="config.yaml")` in `storage/config_loader.py`, used by `main.py`, `web/ai_chat.py`, and `web/routers/subscribe.py`. Missing env vars keep their `${VAR}` literal so callers fail loud (the silent-empty-string substitution in `ai_chat.py` once produced `Authorization: Bearer ` headers in production).

**Source:** final code review during v1 merge.

### ✅ Wire `update_fetch_status` into pipeline (DONE 2026-04-22)
`main._mark_active_sources_fetched(db, status='ok')` runs after every successful collection phase, stamping `last_fetch_at` + `last_fetch_status` on every active user_source. Subscribe management page no longer shows `—` for those fields. Per-feed success/fail granularity is deferred — needs `RSSCollector` to surface per-feed errors, currently they are caught and logged inside `_fetch_feed`.

**Source:** final code review during v1 merge.

### ✅ Dedup static + dynamic source URLs before collection (DONE 2026-04-22)
`_merge_user_sources_into_config` builds a set of existing RSS URLs from static `config.yaml` and skips any user_source whose feed URL is already present. Logged as `Skipped N user_source(s) whose URL was already in static config`.

**Source:** final code review during v1 merge.

### ✅ Refactor `analyze_url` to merge LLM config instead of replacing (DONE 2026-04-22)
`processor/subscribe_analyzer.analyze_url` now does `{**config['llm'], **config.get('subscribe_analyzer', {}).get('llm', {})}`. Top-level `llm` provides `api_key`/`base_url` defaults; the sub-dict only overrides what it sets (e.g. `model`, `temperature`). The duplicated keys added in commit `716baeb` can be removed in a follow-up edit to `config.yaml`.

**Source:** post-deploy hotfix, acknowledged at commit time.

### ✅ Convert `.env` to LF line endings + add `.gitattributes` (DONE pre-2026-04-22)
`.gitattributes` already enforces `* text=auto eol=lf` and an explicit `*.env text eol=lf` line. Future edits from any platform will normalize on commit.

**Source:** rescore-fashion script failed with `Illegal header value b'Bearer sk-xxx '` on 2026-04-21.

---

## Performance

### ✅ Scorer — reuse `httpx.AsyncClient` + concurrent LLM calls (DONE 2026-04-21)
`processor/scorer.py` now builds one `AsyncClient` per `process_items` call and runs items through `asyncio.gather` bounded by `asyncio.Semaphore(llm.max_concurrent)` (default 5, configurable in `config.yaml`). Failures stay isolated per item; tests in `tests/test_scorer_concurrency.py` cover client reuse, peak concurrency, and error isolation.

**Source:** observed during post-deploy fashion rescore (2026-04-21).

### ✅ LLM JSON response parsing is fragile (DONE 2026-04-22)
`AIScorer._parse_json` now tries stdlib `json.loads` first; on `JSONDecodeError` falls back to `json_repair.loads` and emits a `WARNING` log so the failure rate stays observable. Repair handles the four classes of breakage seen in production: unescaped inner double-quotes, trailing commas, missing commas, and partially-fenced markdown. Tests in `tests/test_scorer_json_parse.py` cover each path plus the unrecoverable-garbage case (still raises so the per-item exception handler in `process_items` triggers the existing fallback).

**Source:** pattern observed during 2026-04-21 rescore (~14 of 140 items failed).

---

## Frontend / UX

### ✅ Pinterest-style masonry layout for fashion theme (DONE 2026-04-22)
Implemented as separate `/fashion.html` page with image-first masonry (CSS `column-count`, 1/2/3/4 cols responsive). Image source: direct RSS-extracted URL. Items without an image are filtered out at the API layer (`has_image=true` filter on `/api/news`).

**Decisions taken:**
- Single Fashion tab route → `/fashion.html` (vs. inline template switch on `/`).
- Direct image URL via `<img referrerpolicy="no-referrer">` (no proxy, no cache).
- New tab opens original article (`<a target="_blank">`, no lightbox).
- No-image fashion items completely filtered (no text fallback card).

**Deferred:**
- Backfill of `image_url` for legacy fashion rows — new pipeline runs will populate naturally; old items just won't appear in masonry.
- Image proxy / cache-and-resize — revisit if hotlink bans appear.

**Source:** user request on 2026-04-21 post-deploy.

### 🟡 LEON / Safari / GQ Japan etc. — add RSSHub routes for Japanese fashion magazines
User specifically mentioned interest in Japanese menswear (LEON, Safari). These magazines don't publish public RSS. RSSHub has some community routes that might cover them; otherwise, their 小红书 / 微博 editorial accounts (accessible via the subscription analyzer's RSSHub routes) could serve as content proxies.

**Action:**
1. Audit https://docs.rsshub.app/ for LEON / Safari / GQ Japan routes.
2. If present, add direct entries to `config.yaml` fashion feeds.
3. If absent, document the manual workflow (user pastes their 小红书 profile URL via the subscribe modal).

**Source:** user request on 2026-04-21.

---

## Operational

### ✅ Document deploy-from-behind-company-proxy gotcha (DONE 2026-04-22)
Documented in `docs/OPERATIONS.md` under `## 更新部署` → `### 在办公网络下部署`. Includes both the one-shot HTTPS-via-proxy fetch and the permanent `git remote set-url` + credential helper alternative.

**Source:** v1 deploy 2026-04-21.

### ✅ Clean up accumulated user_sources test rows (DONE 2026-04-22)
The cleanup SQL is documented in `docs/OPERATIONS.md` (`### 一次性维护：清理旧的订阅测试行`). Run on the server when convenient.

**Source:** deploy smoke test artifacts.

### ✅ `.env` hygiene (DONE 2026-04-22)
Audited every `os.getenv()` and `os.environ[...]` call in the runtime. `TWITTER_CT0` and `NEWS_DB_PATH` were used in code but missing from `.env.example` — both now added with placeholder/default values.

---

## Data Quality

### ✅ Expand fashion keyword list in `config.yaml` (DONE 2026-04-22)
`themes.fashion` keywords expanded from ~15 per area to ~30+: designer names (Sarah Burton, Pierpaolo Piccioli, ...), houses (Hermès, Loewe, Bottega Veneta, Kering, LVMH), seasons (SS25/SS26, FW25/FW26, all four fashion weeks), categories beyond apparel (fragrance, perfume, beauty, lip, skincare), and more streetwear/sneaker terms (Stone Island, Yeezy, BAPE, KAWS, vintage, resale, StockX, GOAT, Dunk, Jordan, New Balance).

**Source:** observed during rescore — many Stone Island / PUMA / Kering items defaulted to "其他" from classifier.

---

## Known small bugs

### ✅ Search path in YouTube collector doesn't propagate theme (DONE 2026-04-22)
`YouTubeCollector._search_trending` now reads `cfg.get('theme', 'ai')` and passes it to `_parse_search_item`. Fashion keyword searches under `youtube.search.theme: fashion` will be tagged correctly.

**Source:** final code review during v1 merge.
