# v2 Backlog

Parking lot for follow-up items surfaced during v1 (Fashion Theme + Subscription Analyzer) development and deployment. Each item should eventually get its own spec + plan before implementation.

Items are tagged by priority:
- **🔴 High** — noticeable impact on UX / reliability / cost
- **🟡 Medium** — cleanup / optimization / ergonomics
- **🟢 Low** — nice-to-haves, polish

---

## Architecture & Code Quality

### 🟡 Unify three `load_config` implementations
Three parallel YAML+env-var loaders exist: `main.py:load_config`, `web/ai_chat.py:load_config`, `web/routers/subscribe.py:_load_config_for_analyzer`. They diverge silently on missing env vars (ai_chat falls back to `""`, others keep the `${VAR}` literal). Also each hardcodes `"config.yaml"` relative to cwd.

**Fix:** single utility in `storage/config_loader.py` (or `utils/`), adopted by all three callers.

**Source:** final code review during v1 merge.

### 🟡 Wire `update_fetch_status` into pipeline
`storage/user_sources.update_fetch_status` is defined and unit-tested but never called from `main.py` or collectors. The subscription management page shows `—` for `last_fetch_at` / `last_fetch_status` forever.

**Fix:** call `update_fetch_status(db, src.id, 'ok' | 'fail:<reason>')` after each dynamic source's fetch in the collector loop. Auto-disable source after `consecutive_failures >= 5`.

**Source:** final code review during v1 merge.

### 🟡 Dedup static + dynamic source URLs before collection
`_merge_user_sources_into_config` in `main.py` appends dynamic user_sources unconditionally. If a user subscribes to a URL already in `config.yaml`, it gets fetched twice per pipeline run (DB-level item dedup still prevents duplicate rows, but the network cost is doubled).

**Fix:** normalize + dedup by URL when merging.

**Source:** final code review during v1 merge.

### 🟢 Refactor `analyze_url` to merge LLM config instead of replacing
`analyze_url` reads `subscribe_analyzer.llm` as-is instead of merging it over top-level `llm.*`. This forced us to duplicate `api_key` + `base_url` in the sub-dict (commit `716baeb`). If either is rotated in top-level `llm`, the analyzer silently uses a stale value.

**Fix:** `{**config['llm'], **config.get('subscribe_analyzer', {}).get('llm', {})}`.

**Source:** post-deploy hotfix, acknowledged at commit time.

### 🟢 Convert `.env` to LF line endings + add `.gitattributes`
Server's `.env` has CRLF line endings (Windows-edited), which breaks `source .env` in bash (values get trailing `\r`). systemd and python-dotenv handle it correctly; only manual shell tooling trips on it.

**Fix:** `sed -i 's/\r$//' .env` on server + add `.gitattributes` with `.env text eol=lf` to prevent future edits from re-introducing CRLF.

**Source:** rescore-fashion script failed with `Illegal header value b'Bearer sk-xxx '` on 2026-04-21.

---

## Performance

### ✅ Scorer — reuse `httpx.AsyncClient` + concurrent LLM calls (DONE 2026-04-21)
`processor/scorer.py` now builds one `AsyncClient` per `process_items` call and runs items through `asyncio.gather` bounded by `asyncio.Semaphore(llm.max_concurrent)` (default 5, configurable in `config.yaml`). Failures stay isolated per item; tests in `tests/test_scorer_concurrency.py` cover client reuse, peak concurrency, and error isolation.

**Source:** observed during post-deploy fashion rescore (2026-04-21).

### 🟡 LLM JSON response parsing is fragile
Observed ~10% failure rate of "Expecting ',' delimiter" errors during fashion rescore. Root cause is LLM including unescaped double-quotes inside string values in the JSON response (e.g., article titles like `"It's no surprise..."`).

**Fix options:**
- Prompt: add "use single quotes inside string values" instruction.
- Parser: pre-process LLM response to repair common JSON-quote issues (e.g. use `json-repair` library).
- Request structured output from the LLM API when available.

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

### 🟡 Document deploy-from-behind-company-proxy gotcha
GitHub SSH on the office network is throttled/blocked — pulls hang. HTTPS fetch via the company proxy works:
```bash
timeout 60 git -c http.proxy="$PROXY" -c https.proxy="$PROXY" \
  fetch https://github.com/XD-AIGC/XD-AIGC-ai-news.git main
git merge --ff-only FETCH_HEAD
```
Either switch `origin` URL to HTTPS permanently with a credential helper, or document the HTTPS fallback in `CLAUDE.md` / deploy section.

**Source:** v1 deploy 2026-04-21.

### 🟢 Clean up accumulated user_sources test rows
Several test rows from smoke testing are still in DB (e.g., pending HN RSS, fake.test/feed). Not harmful — they're `status='pending'` so never fetched — but clutters `/api/subscribe/list`.

**Fix:** one-off SQL `DELETE FROM user_sources WHERE status='pending' AND created_at < '2026-04-22'`.

**Source:** deploy smoke test artifacts.

### 🟢 `.env` hygiene
Add `.env.example` RSSHUB_URL line (already done in v1). Audit other env vars used in code — ensure every `os.getenv()` reference is either in `.env.example` with a default OR documented as required.

---

## Data Quality

### 🟡 Expand fashion keyword list in `config.yaml`
Current fashion focus_area keywords miss common terms found in real fashion news (e.g., "tank top", "fragrance", "peptides", "lip treatment", designer names beyond the top ~10). This matters because:
1. `KeywordClassifier` is used as a pre-filter before AI scoring — items not matching keywords fall into "其他" theme bucket and may be filtered out entirely.
2. When LLM scoring fails (see ~10% failure rate above), the fallback sets `ai_categories=['其他']` — classifier-provided categories are already lost.

**Fix:** expand each focus_area keyword list by ~30 terms. Specifically:
- **潮流:** + "New Balance", "Dunk", "Jordan", "collab", "collaboration", "Off-White", "BAPE", "KAWS", "vintage", "resale", "StockX", "GOAT"
- **时装:** + designer names (Sarah Burton, Alessandro Michele, ...), "couture", "atelier", "silhouette", "tailoring", "Met Gala", "ready-to-wear", "RTW", "SS26", "FW26"
- **AI × 时尚:** + "AI-generated", "digital twin", "avatar fashion", "synthetic models"

**Source:** observed during rescore — many Stone Island / PUMA / Kering items defaulted to "其他" from classifier.

---

## Known small bugs

### 🟢 Search path in YouTube collector doesn't propagate theme
`collectors/youtube_collector.py:_fetch_trending` (keyword search) uses the default `Theme.AI` param because search queries aren't per-entry configured. If fashion keyword searches are added later, they'll silently be tagged `ai`.

**Fix:** add a top-level `theme:` field to the `youtube.search` config block and propagate.

**Source:** final code review during v1 merge.
