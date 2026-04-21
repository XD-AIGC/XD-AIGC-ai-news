# Fashion Theme + Subscription Analyzer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fashion/trend content theme alongside the existing AI theme, and give users a UI to paste a URL and have the system analyze+confirm-subscribe it via an LLM-assisted analyzer.

**Architecture:** In-place evolution. Add a two-layer classification (theme → focus_area) without restructuring the pipeline. Dynamic (user-added) sources live in a new DB table and are merged with static config sources at startup. A new backend module (`subscribe_analyzer`) detects URL type, fetches a sample, and uses the existing LLM to recommend theme + focus_areas + quality verdict.

**Tech Stack:** Python 3.10+, pydantic, httpx, FastAPI, SQLite, feedparser, vanilla JS + native `<dialog>`.

**Spec reference:** `docs/superpowers/specs/2026-04-21-fashion-theme-subscription-design.md`

**Key file map (where changes land):**

| File | New / Modified | Responsibility |
|---|---|---|
| `collectors/base.py` | Modified | Add `Theme` enum + `theme` field on `ContentItem` |
| `storage/models.py` | Modified | Add `user_sources` CREATE TABLE |
| `storage/database.py` | Modified | ALTER TABLE to add `theme` column; load `theme` in `_row_to_item`; persist `theme` in `save_items`/`update_ai_results` |
| `storage/user_sources.py` | New | CRUD for `user_sources` table |
| `storage/config_loader.py` | New | Shim reading both legacy `focus_areas` and new `themes` formats |
| `config.yaml` | Modified | Add `themes:` nested config; per-source `theme` field; `rsshub.routes`; `llm.scoring_prompts`; `subscribe_analyzer` section |
| `processor/classifier.py` | Modified | Theme-scoped keyword matching |
| `processor/scorer.py` | Modified | Pick scoring prompt by `item.theme`, keep legacy prompt as default |
| `processor/subscribe_analyzer.py` | New | URL detector chain + sample fetch + LLM analyze orchestration |
| `collectors/rss_collector.py` + others | Modified | Propagate source-level `theme` into emitted `ContentItem` |
| `main.py` | Modified | `build_collectors` merges static + `user_sources(status='active')` |
| `web/app.py` | Modified | Add `theme` query param to `/api/news`; mount `subscribe` router |
| `web/routers/__init__.py`, `web/routers/subscribe.py` | New | Subscribe API endpoints |
| `web/static/index.html`, `app.js`, `style.css` | Modified | Theme tabs, filter propagation, header buttons |
| `web/static/subscribe.html`, `subscribe.js` | New | Subscription management page |
| `web/static/subscribe-modal.js` | New | Analyze-modal logic |
| `scripts/migrate_v2.sql` | New | One-time DB migration |
| `tests/conftest.py` | New | Pytest fixtures (shared httpx mock, in-memory DB) |
| `tests/test_subscribe_analyzer.py` | New | URL detector + orchestrator tests |
| `tests/test_config_loader.py` | New | Shim tests |
| `tests/test_classifier.py` | New | Theme-scoped match tests |
| `requirements-dev.txt` | New | pytest, pytest-asyncio |

**Phasing:** 11 phases, ~38 tasks. Each phase ends with a working, testable state. Commit after every task.

---

## Phase 0 — Test Infrastructure

Lay down pytest scaffolding before anything else. No behavior change yet.

### Task 0.1: Add dev dependencies

**Files:**
- Create: `requirements-dev.txt`

- [ ] **Step 1: Create `requirements-dev.txt`**

Create `requirements-dev.txt` with content:

```
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-cov>=4.1.0
```

- [ ] **Step 2: Install**

Run: `pip install -r requirements-dev.txt`
Expected: installs 3 packages, no errors.

- [ ] **Step 3: Commit**

```bash
git add requirements-dev.txt
git commit -m "test: add pytest dev dependencies"
```

### Task 0.2: Create tests/ directory skeleton

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `pytest.ini`

- [ ] **Step 1: Create empty `tests/__init__.py`**

Write empty file so pytest treats `tests/` as a package.

- [ ] **Step 2: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
asyncio_mode = auto
addopts = -v --tb=short
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

- [ ] **Step 3: Create `tests/conftest.py`** with a temp DB fixture:

```python
"""Shared pytest fixtures."""

import tempfile
from pathlib import Path

import pytest

from storage.database import NewsDatabase


@pytest.fixture
def temp_db(tmp_path: Path) -> NewsDatabase:
    """Fresh SQLite DB per test, cleaned up automatically."""
    db_path = tmp_path / "test.db"
    db = NewsDatabase(str(db_path))
    db.connect()
    yield db
    db.close()
```

- [ ] **Step 4: Verify pytest can discover the directory**

Run: `pytest tests/ -v`
Expected: `no tests ran` (normal — no test files yet), no errors.

- [ ] **Step 5: Commit**

```bash
git add tests/ pytest.ini
git commit -m "test: add pytest scaffolding and temp_db fixture"
```

---

## Phase 1 — Data Model & Config Foundations

Add the `Theme` enum, the DB column, and the config loader shim. No behavior change yet — all items default to `ai`.

### Task 1.1: Add Theme enum + theme field on ContentItem

**Files:**
- Modify: `collectors/base.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_content_item.py`:

```python
"""Tests for ContentItem theme field."""

from collectors.base import ContentItem, SourceType, Theme


def test_content_item_theme_defaults_to_ai():
    item = ContentItem(
        id="x", source_type=SourceType.RSS,
        title="T", url="https://example.com",
    )
    assert item.theme == Theme.AI


def test_content_item_accepts_fashion_theme():
    item = ContentItem(
        id="x", source_type=SourceType.RSS,
        title="T", url="https://example.com",
        theme=Theme.FASHION,
    )
    assert item.theme == Theme.FASHION


def test_theme_enum_values():
    assert Theme.AI.value == "ai"
    assert Theme.FASHION.value == "fashion"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_content_item.py -v`
Expected: FAIL (ImportError: cannot import name 'Theme').

- [ ] **Step 3: Add Theme enum and field**

In `collectors/base.py`, add after the `SourceType` enum:

```python
class Theme(str, Enum):
    AI = "ai"
    FASHION = "fashion"
```

And on `ContentItem`, add the field:

```python
class ContentItem(BaseModel):
    """Unified content item from any source."""

    id: str
    source_type: SourceType
    title: str
    url: str
    content: str = ""
    author: str = ""
    published_at: Optional[datetime] = None
    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = Field(default_factory=dict)
    theme: Theme = Theme.AI   # NEW: default preserves legacy behavior

    # AI processing results (filled in Phase 3)
    ai_score: Optional[float] = None
    ai_summary: Optional[str] = None
    ai_categories: list[str] = Field(default_factory=list)
    ai_tags: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_content_item.py -v`
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add collectors/base.py tests/test_content_item.py
git commit -m "feat: add Theme enum and theme field on ContentItem"
```

### Task 1.2: DB migration — add theme column to news table

**Files:**
- Modify: `storage/models.py`
- Modify: `storage/database.py`
- Create: `scripts/migrate_v2.sql`

- [ ] **Step 1: Write the failing test**

Create `tests/test_database_theme.py`:

```python
"""Tests for theme column on news table."""

from datetime import datetime, timezone

from collectors.base import ContentItem, SourceType, Theme


def test_save_and_load_item_with_theme(temp_db):
    item = ContentItem(
        id="x1",
        source_type=SourceType.RSS,
        title="Fashion news",
        url="https://example.com/1",
        theme=Theme.FASHION,
    )
    temp_db.save_items([item])
    loaded = temp_db.get_items_by_date(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    assert len(loaded) == 1
    assert loaded[0].theme == Theme.FASHION


def test_default_theme_is_ai_for_legacy_rows(temp_db):
    # Insert a row without theme via raw SQL to simulate legacy data
    cursor = temp_db._conn.cursor()
    cursor.execute(
        """INSERT INTO news (id, source_type, title, url, collected_at)
           VALUES (?, ?, ?, ?, ?)""",
        ("legacy1", "rss", "Old item", "https://example.com/old",
         datetime.now(timezone.utc).isoformat()),
    )
    temp_db._conn.commit()

    loaded = temp_db.get_items_by_date(datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    assert len(loaded) == 1
    assert loaded[0].theme == Theme.AI
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_database_theme.py -v`
Expected: FAIL (theme column doesn't exist, or `_row_to_item` doesn't read it).

- [ ] **Step 3: Update schema in `storage/models.py`**

Modify the `CREATE_NEWS_TABLE` constant (for fresh installs):

```python
CREATE_NEWS_TABLE = """
CREATE TABLE IF NOT EXISTS news (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    content TEXT DEFAULT '',
    author TEXT DEFAULT '',
    published_at TEXT,
    collected_at TEXT NOT NULL,
    metadata_json TEXT DEFAULT '{}',
    ai_score REAL,
    ai_summary TEXT,
    ai_categories TEXT DEFAULT '[]',
    ai_tags TEXT DEFAULT '[]',
    theme TEXT NOT NULL DEFAULT 'ai',
    created_at TEXT DEFAULT (datetime('now'))
);
"""

CREATE_INDEX_THEME = """
CREATE INDEX IF NOT EXISTS idx_news_theme ON news(theme);
"""
```

- [ ] **Step 4: Add idempotent in-code migration in `storage/database.py`**

In `_init_tables`, after existing `cursor.execute(...)` calls, add:

```python
from storage.models import (
    CREATE_INDEX_DATE, CREATE_INDEX_SCORE, CREATE_INDEX_SOURCE,
    CREATE_INDEX_URL, CREATE_INDEX_THEME, CREATE_NEWS_TABLE,
)

def _init_tables(self) -> None:
    cursor = self._conn.cursor()
    cursor.execute(CREATE_NEWS_TABLE)
    cursor.execute(CREATE_INDEX_URL)
    cursor.execute(CREATE_INDEX_DATE)
    cursor.execute(CREATE_INDEX_SOURCE)
    cursor.execute(CREATE_INDEX_SCORE)

    # Migration: add theme column if it doesn't exist (idempotent)
    cursor.execute("PRAGMA table_info(news)")
    cols = {row[1] for row in cursor.fetchall()}
    if "theme" not in cols:
        cursor.execute("ALTER TABLE news ADD COLUMN theme TEXT NOT NULL DEFAULT 'ai'")
        logger.info("Migrated: added 'theme' column to news table")

    cursor.execute(CREATE_INDEX_THEME)
    self._conn.commit()
```

- [ ] **Step 5: Update `save_items` to persist theme**

In `save_items`, extend the INSERT statement:

```python
cursor.execute(
    """INSERT INTO news
    (id, source_type, title, url, content, author,
     published_at, collected_at, metadata_json,
     ai_score, ai_summary, ai_categories, ai_tags, theme)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
    (
        item.id,
        item.source_type.value,
        item.title,
        item.url,
        item.content,
        item.author,
        item.published_at.isoformat() if item.published_at else None,
        item.collected_at.isoformat(),
        json.dumps(item.metadata, ensure_ascii=False),
        item.ai_score,
        item.ai_summary,
        json.dumps(item.ai_categories, ensure_ascii=False),
        json.dumps(item.ai_tags, ensure_ascii=False),
        item.theme.value,
    ),
)
```

- [ ] **Step 6: Update `_row_to_item` to read theme**

```python
def _row_to_item(self, row: sqlite3.Row) -> ContentItem:
    from collectors.base import Theme
    # Row may not have theme column if from pre-migration; default to ai
    try:
        theme_value = row["theme"] or "ai"
    except (KeyError, IndexError):
        theme_value = "ai"

    return ContentItem(
        id=row["id"],
        source_type=row["source_type"],
        title=row["title"],
        url=row["url"],
        content=row["content"] or "",
        author=row["author"] or "",
        published_at=datetime.fromisoformat(row["published_at"])
        if row["published_at"]
        else None,
        collected_at=datetime.fromisoformat(row["collected_at"]),
        metadata=json.loads(row["metadata_json"] or "{}"),
        ai_score=row["ai_score"],
        ai_summary=row["ai_summary"],
        ai_categories=json.loads(row["ai_categories"] or "[]"),
        ai_tags=json.loads(row["ai_tags"] or "[]"),
        theme=Theme(theme_value),
    )
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/test_database_theme.py tests/test_content_item.py -v`
Expected: 5 tests pass.

- [ ] **Step 8: Create manual migration script**

Create `scripts/migrate_v2.sql`:

```sql
-- Migration v2: add theme column, create user_sources table
-- Run once per environment:  sqlite3 data/news.db < scripts/migrate_v2.sql
--
-- Safe to re-run: column add is guarded by PRAGMA check in database.py at runtime,
-- but if you want to migrate offline, run these statements manually.

BEGIN TRANSACTION;

-- Add theme column (fails silently if already exists; SQLite has no IF NOT EXISTS for ADD COLUMN,
-- so use the Python code path for idempotency; this file is for explicit offline migrations).
ALTER TABLE news ADD COLUMN theme TEXT NOT NULL DEFAULT 'ai';
CREATE INDEX IF NOT EXISTS idx_news_theme ON news(theme);

-- Create user_sources table (Phase 5 will populate the spec for this)
-- NOTE: full user_sources schema is created by Phase 5 migration task.
-- This file will be updated at that point.

COMMIT;
```

- [ ] **Step 9: Commit**

```bash
git add storage/models.py storage/database.py scripts/migrate_v2.sql tests/test_database_theme.py
git commit -m "feat: add theme column to news table with auto-migration"
```

### Task 1.3: Config loader shim for themes vs focus_areas

**Files:**
- Create: `storage/config_loader.py`
- Create: `tests/test_config_loader.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config_loader.py`:

```python
"""Tests for load_themes shim."""

from storage.config_loader import load_themes


def test_load_new_themes_format():
    config = {
        "themes": {
            "ai": [{"name": "开源模型", "keywords": ["stable diffusion"]}],
            "fashion": [{"name": "潮流", "keywords": ["streetwear"]}],
        }
    }
    themes = load_themes(config)
    assert "ai" in themes
    assert "fashion" in themes
    assert themes["ai"][0]["name"] == "开源模型"


def test_load_legacy_focus_areas_wraps_into_ai():
    config = {
        "focus_areas": [{"name": "ComfyUI", "keywords": ["comfyui"]}]
    }
    themes = load_themes(config)
    assert "ai" in themes
    assert len(themes["ai"]) == 1
    assert themes["ai"][0]["name"] == "ComfyUI"
    assert "fashion" not in themes


def test_load_empty_config_returns_empty_ai():
    themes = load_themes({})
    assert themes == {"ai": []}


def test_themes_takes_precedence_over_focus_areas():
    # If both are present (shouldn't happen but be defensive), themes wins
    config = {
        "themes": {"ai": [{"name": "A", "keywords": []}]},
        "focus_areas": [{"name": "B", "keywords": []}],
    }
    themes = load_themes(config)
    assert themes["ai"][0]["name"] == "A"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_loader.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement the shim**

Create `storage/config_loader.py`:

```python
"""Config loader shim supporting both legacy focus_areas and new themes formats."""

import logging

logger = logging.getLogger(__name__)


def load_themes(config: dict) -> dict[str, list[dict]]:
    """Return themes mapping from config, accepting legacy or new format.

    New format (preferred):
        themes:
          ai: [ {name, keywords}, ... ]
          fashion: [ ... ]

    Legacy format:
        focus_areas: [ {name, keywords}, ... ]
        -> wrapped as {"ai": [...]}
    """
    if "themes" in config and isinstance(config["themes"], dict):
        return config["themes"]

    if "focus_areas" in config:
        logger.info(
            "Legacy 'focus_areas' config detected, wrapping as themes.ai. "
            "Consider migrating to the 'themes' format."
        )
        return {"ai": config["focus_areas"]}

    return {"ai": []}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_config_loader.py -v`
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add storage/config_loader.py tests/test_config_loader.py
git commit -m "feat: add config loader shim for themes / focus_areas compatibility"
```

---

## Phase 2 — Theme-Scoped Classifier

Refactor `KeywordClassifier` so AI items don't match fashion focus_areas, and vice versa.

### Task 2.1: Refactor KeywordClassifier to accept themes mapping

**Files:**
- Modify: `processor/classifier.py`
- Create: `tests/test_classifier.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_classifier.py`:

```python
"""Tests for theme-scoped KeywordClassifier."""

from collectors.base import ContentItem, SourceType, Theme
from processor.classifier import KeywordClassifier


THEMES = {
    "ai": [
        {"name": "开源模型", "keywords": ["stable diffusion", "flux"]},
        {"name": "ComfyUI", "keywords": ["comfyui"]},
    ],
    "fashion": [
        {"name": "潮流", "keywords": ["streetwear", "hypebeast"]},
        {"name": "时装", "keywords": ["runway", "vogue"]},
    ],
}


def _make_item(title: str, theme: Theme = Theme.AI) -> ContentItem:
    return ContentItem(
        id="x", source_type=SourceType.RSS,
        title=title, url="https://example.com", theme=theme,
    )


def test_ai_item_matches_ai_focus_area():
    c = KeywordClassifier(THEMES)
    item = _make_item("New Stable Diffusion release", Theme.AI)
    result = c.classify(item)
    assert "开源模型" in result


def test_ai_item_does_not_match_fashion_focus_area():
    # Even if title contains "streetwear", AI item stays in AI theme
    c = KeywordClassifier(THEMES)
    item = _make_item("AI generated streetwear designs", Theme.AI)
    result = c.classify(item)
    # Should NOT contain fashion categories
    assert "潮流" not in result


def test_fashion_item_matches_fashion_focus_area():
    c = KeywordClassifier(THEMES)
    item = _make_item("New Vogue runway report", Theme.FASHION)
    result = c.classify(item)
    assert "时装" in result


def test_fashion_item_does_not_match_ai_focus_area():
    c = KeywordClassifier(THEMES)
    item = _make_item("Fashion with stable diffusion tools", Theme.FASHION)
    result = c.classify(item)
    assert "开源模型" not in result


def test_no_match_falls_back_to_qita():
    c = KeywordClassifier(THEMES)
    item = _make_item("Totally unrelated content", Theme.AI)
    result = c.classify(item)
    assert result == ["其他"]


def test_filter_relevant_excludes_qita():
    c = KeywordClassifier(THEMES)
    items = [
        _make_item("Stable Diffusion release", Theme.AI),
        _make_item("Unrelated random text", Theme.AI),
    ]
    filtered = c.filter_relevant(items)
    assert len(filtered) == 1
    assert filtered[0].title == "Stable Diffusion release"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_classifier.py -v`
Expected: FAIL (classifier doesn't accept themes mapping yet, or matches across themes).

- [ ] **Step 3: Rewrite `processor/classifier.py`**

Replace the full contents with:

```python
"""Theme-scoped keyword classifier (no LLM required)."""

import logging

from collectors.base import ContentItem, Theme

logger = logging.getLogger(__name__)


class KeywordClassifier:
    """Classify items into focus areas, scoped to the item's theme.

    An AI item only matches keywords from themes['ai']; a fashion item only
    matches keywords from themes['fashion']. This prevents cross-theme mis-tagging.
    """

    def __init__(self, themes: dict[str, list[dict]]):
        # themes is {"ai": [{name, keywords}, ...], "fashion": [...]}
        self.themes: dict[str, list[tuple[str, set[str]]]] = {}
        for theme_name, areas in themes.items():
            compiled: list[tuple[str, set[str]]] = []
            for area in areas:
                name = area["name"]
                keywords = {kw.lower() for kw in area.get("keywords", [])}
                compiled.append((name, keywords))
            self.themes[theme_name] = compiled

    def classify(self, item: ContentItem) -> list[str]:
        """Return matching focus area names, scoped to item's theme."""
        theme_key = item.theme.value if isinstance(item.theme, Theme) else item.theme
        areas = self.themes.get(theme_key, [])
        if not areas:
            return ["其他"]

        text = f"{item.title} {item.content[:500]}".lower()
        matches = []
        for name, keywords in areas:
            if any(kw in text for kw in keywords):
                matches.append(name)
        return matches if matches else ["其他"]

    def classify_items(
        self, items: list[ContentItem], overwrite: bool = False
    ) -> list[ContentItem]:
        """Classify items that don't already have categories."""
        classified = 0
        for item in items:
            if item.ai_categories and not overwrite:
                continue
            item.ai_categories = self.classify(item)
            classified += 1

        logger.info("Keyword classifier: classified %d items", classified)
        return items

    def filter_relevant(self, items: list[ContentItem]) -> list[ContentItem]:
        """Keep only items matching at least one focus area (not '其他')."""
        relevant = []
        for item in items:
            cats = self.classify(item)
            if cats != ["其他"]:
                relevant.append(item)

        logger.info("Relevance filter: %d -> %d items", len(items), len(relevant))
        return relevant
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_classifier.py -v`
Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add processor/classifier.py tests/test_classifier.py
git commit -m "refactor: theme-scoped KeywordClassifier (items match only their own theme)"
```

### Task 2.2: Wire new classifier into main.py

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Replace focus_areas usage with themes shim**

In `main.py`, replace the classification section (around lines 222-227 of current `run()`):

```python
# Keyword pre-classification
from storage.config_loader import load_themes
themes = load_themes(config)
if any(themes.values()):
    classifier = KeywordClassifier(themes)
    items = classifier.classify_items(items)
```

Also replace the pre-filter section (around lines 248-255):

```python
# Pre-filter: only score items matching focus areas
if unscored and any(themes.values()):
    pre_filter = KeywordClassifier(themes)
    before = len(unscored)
    unscored = pre_filter.filter_relevant(unscored)
    logger.info(
        "Pre-filter for AI scoring: %d -> %d items",
        before, len(unscored),
    )
```

Remove the old `focus_areas = config.get("focus_areas", [])` line — `themes` replaces it.

- [ ] **Step 2: Smoke test — run pipeline on existing config**

Run: `python main.py --skip-ai --no-proxy --days 1 -v`
Expected: runs without errors; log shows `Legacy 'focus_areas' config detected, wrapping as themes.ai` (because `config.yaml` still uses old format at this point).

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "refactor: main.py uses load_themes shim for classifier input"
```

---

## Phase 3 — Per-Theme Scoring Prompts

Make `AIScorer` pick a prompt matching the item's theme.

### Task 3.1: AIScorer accepts per-theme prompts

**Files:**
- Modify: `processor/scorer.py`
- Create: `tests/test_scorer_theme.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_scorer_theme.py`:

```python
"""Tests for per-theme prompt selection in AIScorer."""

from collectors.base import ContentItem, SourceType, Theme
from processor.scorer import AIScorer


def test_scorer_picks_theme_prompt():
    config = {
        "model": "fake-model",
        "api_key": "fake",
        "scoring_prompts": {
            "ai": "AI ANALYST PROMPT",
            "fashion": "FASHION ANALYST PROMPT",
        },
    }
    scorer = AIScorer(config)

    ai_item = ContentItem(
        id="1", source_type=SourceType.RSS, title="T", url="u",
        theme=Theme.AI,
    )
    fashion_item = ContentItem(
        id="2", source_type=SourceType.RSS, title="T", url="u",
        theme=Theme.FASHION,
    )

    assert "AI ANALYST" in scorer._system_prompt_for(ai_item)
    assert "FASHION ANALYST" in scorer._system_prompt_for(fashion_item)


def test_scorer_falls_back_to_legacy_prompt_when_no_scoring_prompts():
    # Back-compat: if config has no scoring_prompts, use the module-level SYSTEM_PROMPT
    from processor.scorer import SYSTEM_PROMPT

    config = {"model": "m", "api_key": "k"}  # no scoring_prompts
    scorer = AIScorer(config)

    item = ContentItem(
        id="1", source_type=SourceType.RSS, title="T", url="u",
        theme=Theme.AI,
    )
    assert scorer._system_prompt_for(item) == SYSTEM_PROMPT


def test_scorer_missing_theme_prompt_falls_back_to_ai_prompt():
    config = {
        "model": "m", "api_key": "k",
        "scoring_prompts": {"ai": "AI PROMPT"},  # fashion missing
    }
    scorer = AIScorer(config)

    fashion_item = ContentItem(
        id="1", source_type=SourceType.RSS, title="T", url="u",
        theme=Theme.FASHION,
    )
    # Missing → fall back to ai
    assert scorer._system_prompt_for(fashion_item) == "AI PROMPT"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scorer_theme.py -v`
Expected: FAIL (`_system_prompt_for` doesn't exist).

- [ ] **Step 3: Modify `AIScorer.__init__` + add `_system_prompt_for`**

In `processor/scorer.py`:

1. In `__init__`, store scoring_prompts:

```python
def __init__(self, config: dict):
    self.model = config.get("model", "gpt-4o-mini")
    self.api_key = config.get("api_key", "")
    self.base_url = config.get("base_url", "https://api.openai.com/v1")
    self.temperature = config.get("temperature", 0.3)
    self.threshold = config.get("score_threshold", 6.0)
    self.proxy = config.get("proxy")
    self.scoring_prompts: dict[str, str] = config.get("scoring_prompts", {})
```

2. Add helper method:

```python
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
```

3. Update `_score_item` to use it:

```python
async def _score_item(self, item: ContentItem) -> None:
    # ... existing content_preview code ...

    system_prompt = self._system_prompt_for(item)

    # ... existing user_prompt / httpx code, but replace:
    #     {"role": "system", "content": SYSTEM_PROMPT}
    # with:
    #     {"role": "system", "content": system_prompt}
```

- [ ] **Step 4: Import ContentItem type hint at top of scorer.py if not already**

Already imported. No change.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_scorer_theme.py -v`
Expected: 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add processor/scorer.py tests/test_scorer_theme.py
git commit -m "feat: AIScorer picks per-theme scoring prompt with fallbacks"
```

### Task 3.2: Add fashion scoring prompt to config.yaml

**Files:**
- Modify: `config.yaml`

- [ ] **Step 1: Add `scoring_prompts` block under `llm:`**

Find the `llm:` section in `config.yaml` and add:

```yaml
llm:
  provider: "openai"
  model: "claude-sonnet-4-6"
  api_key: "${OPENAI_API_KEY}"
  base_url: "${OPENAI_BASE_URL}"
  temperature: 0.3
  score_threshold: 6.0
  scoring_prompts:
    ai: |
      你是一个专业的 AI 科技资讯评审专家，专注于以下领域：
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
      - 0-2: 噪音，不相关或低质量
    fashion: |
      你是一个专业的时尚潮流趋势分析师，关注以下领域：
      - 潮流 (街头穿搭、球鞋文化、国潮、潮牌、hype drop)
      - 时装 (时装周、秀场、设计师、奢侈品、高定、四大时装周)
      - AI × 时尚 (AI 虚拟模特、AIGC 服装、数字时尚、AI 穿搭工具)

      请对每条资讯进行评分和分析。评分标准：
      - 9-10: 重大趋势、标志性发布、行业地震级事件
      - 7-8: 重要品牌动态、值得立即关注的设计/联名/秀场
      - 5-6: 有趣但非紧急的趋势观察、穿搭灵感
      - 3-4: 常规发布、通用内容
      - 0-2: 纯带货、营销噪音、与时尚/潮流无关
```

- [ ] **Step 2: Smoke test (skip AI, just ensure config loads)**

Run: `python -c "import yaml; yaml.safe_load(open('config.yaml'))"`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add config.yaml
git commit -m "config: add per-theme scoring prompts (ai + fashion)"
```

---

## Phase 4 — Source-Declared Theme

Make each source config entry optionally carry a `theme`, and propagate it to every emitted `ContentItem`.

### Task 4.1: RSS collector propagates per-feed theme

**Files:**
- Modify: `collectors/rss_collector.py`
- Create: `tests/test_rss_theme.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_rss_theme.py`:

```python
"""Tests for RSSCollector propagating per-feed theme into ContentItem."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from collectors.base import Theme
from collectors.rss_collector import RSSCollector


@pytest.mark.asyncio
async def test_rss_propagates_feed_theme_to_items(monkeypatch):
    sample_rss = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <title>Test Feed</title>
      <item>
        <title>Hello</title>
        <link>https://example.com/1</link>
        <pubDate>Mon, 21 Apr 2026 10:00:00 +0000</pubDate>
      </item>
    </channel></rss>"""

    client = AsyncMock()
    response = MagicMock()
    response.text = sample_rss
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    feeds = [
        {"url": "https://hypebeast.com/feed", "name": "Hypebeast", "theme": "fashion"},
    ]
    collector = RSSCollector(feeds, client)

    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    items = await collector.fetch(since)

    assert len(items) == 1
    assert items[0].theme == Theme.FASHION


@pytest.mark.asyncio
async def test_rss_defaults_to_ai_when_theme_not_set(monkeypatch):
    sample_rss = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item>
        <title>Hello</title>
        <link>https://example.com/1</link>
        <pubDate>Mon, 21 Apr 2026 10:00:00 +0000</pubDate>
      </item>
    </channel></rss>"""

    client = AsyncMock()
    response = MagicMock()
    response.text = sample_rss
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    feeds = [{"url": "https://openai.com/blog/rss.xml", "name": "OpenAI"}]
    collector = RSSCollector(feeds, client)
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    items = await collector.fetch(since)

    assert items[0].theme == Theme.AI
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_rss_theme.py -v`
Expected: FAIL (theme not set from feed config).

- [ ] **Step 3: Modify RSS collector**

In `collectors/rss_collector.py`, inside `_fetch_feed`, read the theme and set it:

```python
async def _fetch_feed(
    self, feed_cfg: dict, since: datetime
) -> list[ContentItem]:
    url = feed_cfg["url"]
    name = feed_cfg.get("name", url)
    theme = Theme(feed_cfg.get("theme", "ai"))   # NEW
    items: list[ContentItem] = []

    try:
        # ... existing fetch + parse code ...

        for entry in feed.entries:
            # ... existing entry processing ...

            item = ContentItem(
                id=self._generate_id(
                    self.source_type.value, name.replace(" ", "_"), uid
                ),
                source_type=self.source_type,
                title=entry.get("title", "Untitled"),
                url=entry.get("link", url),
                content=self._extract_content(entry),
                author=entry.get("author", name),
                published_at=published_at,
                theme=theme,    # NEW
                metadata={
                    "feed_name": name,
                    "tags": [t.term for t in entry.get("tags", [])],
                },
            )
            items.append(item)
```

Import `Theme` at top of file:

```python
from collectors.base import BaseScraper, ContentItem, SourceType, Theme
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_rss_theme.py -v`
Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add collectors/rss_collector.py tests/test_rss_theme.py
git commit -m "feat: RSSCollector propagates per-feed theme to items"
```

### Task 4.2: Other collectors propagate theme (YouTube, Twitter, Bilibili, Reddit, Telegram)

**Files:**
- Modify: `collectors/youtube_collector.py`, `collectors/bilibili_collector.py`, `collectors/twitter_collector.py`, `collectors/reddit_collector.py`, `collectors/telegram_collector.py`

- [ ] **Step 1: For each collector, apply the same pattern as RSS**

For YouTube, the per-channel config is `sources.youtube.channels[i]`. Modify the loop that emits items:

```python
# In youtube_collector.py, inside per-channel loop
theme = Theme(channel_cfg.get("theme", "ai"))
# ... when constructing ContentItem, add theme=theme
```

Apply the same pattern to:
- `bilibili_collector.py`: per-user config `bili_cfg["users"][i]`
- `twitter_collector.py`: per-user config `tw_cfg["users"][i]`
- `reddit_collector.py`: per-subreddit `reddit_cfg["subreddits"][i]`
- `telegram_collector.py`: per-channel `telegram_cfg["channels"][i]`

In each: import `Theme`, read `theme = Theme(entry.get("theme", "ai"))`, set `theme=theme` on emitted `ContentItem`.

- [ ] **Step 2: Smoke test on one collector (no network)**

Verify no syntax errors by importing:

Run: `python -c "from collectors.youtube_collector import YouTubeCollector; print('ok')"`
Run: `python -c "from collectors.bilibili_collector import BilibiliCollector; print('ok')"`
Run: `python -c "from collectors.twitter_collector import TwitterCollector; print('ok')"`
Run: `python -c "from collectors.reddit_collector import RedditCollector; print('ok')"`
Run: `python -c "from collectors.telegram_collector import TelegramCollector; print('ok')"`

Expected: all print `ok`.

- [ ] **Step 3: Commit**

```bash
git add collectors/
git commit -m "feat: all collectors propagate per-source theme to items"
```

### Task 4.3: Migrate config.yaml to themes format + add fashion sources

**Files:**
- Modify: `config.yaml`

- [ ] **Step 1: Replace `focus_areas:` top-level key with `themes:`**

Structure the top:

```yaml
themes:
  ai:
    - name: "开源模型"
      keywords: ["open source", "开源", "weights release", "model release", "Stable Diffusion", "Flux", "HunyuanVideo", "CogView", "Wan", "LoRA", "Hugging Face"]
    - name: "ComfyUI"
      keywords: ["ComfyUI", "custom node", "workflow", "comfy", "ComfyUI-Manager"]
    - name: "商用产品"
      keywords: ["Lovart", "Gemini", "GPT", "OpenAI", "Claude", "Anthropic", "Midjourney", "DALL-E", "Sora", "Runway"]
    - name: "Agent & Skills"
      keywords: ["agent", "MCP", "mcp-server", "model context protocol", "tool use", "function calling", "autonomous", "agentic", "cursor", "copilot", "claude code", "claude-code", "skills", "coding agent", "vibe-coding", "ai coding"]
    - name: "3D生成与重建"
      keywords: ["gaussian splatting", "3DGS", "4DGS", "NeRF", "neural rendering", "3D reconstruction", "3D generation", "text-to-3d", "point cloud", "mesh generation", "radiance field"]
    - name: "训练与部署"
      keywords: ["fine-tune", "training", "LoRA", "RLHF", "inference", "quantization", "deployment", "distillation"]
  fashion:
    - name: "潮流"
      keywords: ["streetwear", "街头", "sneakers", "球鞋", "Supreme", "Stussy", "国潮", "Hypebeast", "Highsnobiety", "hype", "drop", "fashion", "潮牌", "Nike", "adidas"]
    - name: "时装"
      keywords: ["runway", "时装周", "秀场", "haute couture", "Vogue", "LV", "Louis Vuitton", "Prada", "Gucci", "Chanel", "BoF", "luxury", "designer", "collection", "couture", "Dior"]
    - name: "AI × 时尚"
      keywords: ["AI fashion", "virtual model", "digital fashion", "AIGC 服装", "AI 穿搭", "virtual try-on", "AI runway", "generative fashion", "AI 时装"]
```

- [ ] **Step 2: Add fashion RSS feeds under `sources.rss.feeds`**

Append to the existing feeds list:

```yaml
      # Fashion feeds
      - { url: "https://hypebeast.com/feed", name: "Hypebeast", theme: "fashion" }
      - { url: "https://www.businessoffashion.com/feed", name: "Business of Fashion", theme: "fashion" }
      - { url: "https://www.highsnobiety.com/feed", name: "Highsnobiety", theme: "fashion" }
      - { url: "https://www.vogue.com/feed/rss", name: "Vogue", theme: "fashion" }
      - { url: "https://www.dezeen.com/feed/", name: "Dezeen", theme: "fashion" }
```

(If any of these URLs no longer publish an RSS feed by implementation time, swap to a functional one. These are starting points.)

- [ ] **Step 3: Smoke test — config loads and pipeline runs**

Run: `python main.py --skip-ai --no-proxy --days 1 -v 2>&1 | head -80`
Expected:
- No `Legacy 'focus_areas'` warning (we migrated the format)
- Fashion RSS feeds show up in collector logs
- Items saved without errors

- [ ] **Step 4: Commit**

```bash
git add config.yaml
git commit -m "config: migrate to themes format and add fashion RSS seed sources"
```

---

## Phase 5 — user_sources Table + Dynamic Source Merging

Add persistence for user-added subscriptions. Pipeline merges static + dynamic sources at startup.

### Task 5.1: Add user_sources table schema

**Files:**
- Modify: `storage/models.py`
- Modify: `scripts/migrate_v2.sql`

- [ ] **Step 1: Add schema to models.py**

Append to `storage/models.py`:

```python
CREATE_USER_SOURCES_TABLE = """
CREATE TABLE IF NOT EXISTS user_sources (
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
    created_at TEXT DEFAULT (datetime('now')),
    activated_at TEXT,
    last_fetch_at TEXT,
    last_fetch_status TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    name TEXT
);
"""

CREATE_INDEX_USER_SOURCES_STATUS = """
CREATE INDEX IF NOT EXISTS idx_user_sources_status ON user_sources(status);
"""
```

- [ ] **Step 2: Register in database.py `_init_tables`**

```python
from storage.models import (
    CREATE_INDEX_DATE, CREATE_INDEX_SCORE, CREATE_INDEX_SOURCE,
    CREATE_INDEX_URL, CREATE_INDEX_THEME, CREATE_NEWS_TABLE,
    CREATE_USER_SOURCES_TABLE, CREATE_INDEX_USER_SOURCES_STATUS,
)

def _init_tables(self) -> None:
    cursor = self._conn.cursor()
    cursor.execute(CREATE_NEWS_TABLE)
    cursor.execute(CREATE_INDEX_URL)
    cursor.execute(CREATE_INDEX_DATE)
    cursor.execute(CREATE_INDEX_SOURCE)
    cursor.execute(CREATE_INDEX_SCORE)

    # Migration: add theme column if missing
    cursor.execute("PRAGMA table_info(news)")
    cols = {row[1] for row in cursor.fetchall()}
    if "theme" not in cols:
        cursor.execute("ALTER TABLE news ADD COLUMN theme TEXT NOT NULL DEFAULT 'ai'")
        logger.info("Migrated: added 'theme' column to news table")

    cursor.execute(CREATE_INDEX_THEME)
    cursor.execute(CREATE_USER_SOURCES_TABLE)
    cursor.execute(CREATE_INDEX_USER_SOURCES_STATUS)
    self._conn.commit()
```

- [ ] **Step 3: Update migrate_v2.sql**

Replace existing content of `scripts/migrate_v2.sql`:

```sql
-- Migration v2: add theme column, create user_sources table
-- Run once per environment: sqlite3 data/news.db < scripts/migrate_v2.sql
-- (Or rely on auto-migration in storage/database.py on next startup.)

BEGIN TRANSACTION;

-- 1) Add theme column to news (fails if already exists; in that case skip)
ALTER TABLE news ADD COLUMN theme TEXT NOT NULL DEFAULT 'ai';
CREATE INDEX IF NOT EXISTS idx_news_theme ON news(theme);

-- 2) Create user_sources table
CREATE TABLE IF NOT EXISTS user_sources (
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
    created_at TEXT DEFAULT (datetime('now')),
    activated_at TEXT,
    last_fetch_at TEXT,
    last_fetch_status TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    name TEXT
);
CREATE INDEX IF NOT EXISTS idx_user_sources_status ON user_sources(status);

COMMIT;
```

- [ ] **Step 4: Verify table creation**

Run: `python -c "from storage.database import NewsDatabase; db = NewsDatabase('./data/news.db'); db.connect(); db.close(); print('ok')"`
Expected: `ok`. Table created / migrated on connect.

Verify:
Run: `sqlite3 ./data/news.db ".schema user_sources"`
Expected: schema printed showing all columns.

- [ ] **Step 5: Commit**

```bash
git add storage/models.py storage/database.py scripts/migrate_v2.sql
git commit -m "feat: add user_sources table with auto-migration"
```

### Task 5.2: user_sources CRUD module

**Files:**
- Create: `storage/user_sources.py`
- Create: `tests/test_user_sources.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_user_sources.py`:

```python
"""Tests for user_sources CRUD."""

import json

from storage.user_sources import (
    UserSource, compute_url_hash, insert_user_source,
    get_by_url_hash, list_by_status, update_status,
    update_fetch_status,
)


def test_compute_url_hash_normalizes():
    # Same URL with/without trailing slash, fragment → same hash
    assert compute_url_hash("https://example.com/feed") == compute_url_hash("https://example.com/feed/")
    assert compute_url_hash("https://EXAMPLE.com/feed") == compute_url_hash("https://example.com/feed")
    assert compute_url_hash("https://example.com/feed#top") == compute_url_hash("https://example.com/feed")


def test_insert_and_get_user_source(temp_db):
    src = UserSource(
        url="https://hypebeast.com/feed",
        url_hash=compute_url_hash("https://hypebeast.com/feed"),
        status="pending",
        source_type="rss",
        normalized_config=json.dumps({"feed_url": "https://hypebeast.com/feed"}),
        theme="fashion",
        focus_areas=json.dumps(["潮流"]),
        llm_reasoning="...",
        sample_json=json.dumps([]),
        name="Hypebeast",
    )
    sid = insert_user_source(temp_db, src)
    assert sid > 0

    got = get_by_url_hash(temp_db, src.url_hash)
    assert got is not None
    assert got.url == "https://hypebeast.com/feed"
    assert got.theme == "fashion"


def test_update_status_to_active(temp_db):
    src = UserSource(
        url="https://x.com/feed",
        url_hash=compute_url_hash("https://x.com/feed"),
        status="pending",
        source_type="rss",
        normalized_config="{}",
        theme="ai",
        focus_areas="[]",
        llm_reasoning="",
        sample_json="[]",
        name="X",
    )
    sid = insert_user_source(temp_db, src)
    update_status(temp_db, sid, "active")
    got = get_by_url_hash(temp_db, src.url_hash)
    assert got.status == "active"
    assert got.activated_at is not None


def test_list_by_status_returns_only_matching(temp_db):
    for i, status in enumerate(["pending", "active", "active", "rejected"]):
        src = UserSource(
            url=f"https://example.com/{i}",
            url_hash=compute_url_hash(f"https://example.com/{i}"),
            status=status,
            source_type="rss", normalized_config="{}",
            theme="ai", focus_areas="[]",
            llm_reasoning="", sample_json="[]", name=f"S{i}",
        )
        insert_user_source(temp_db, src)

    active = list_by_status(temp_db, "active")
    assert len(active) == 2

    pending = list_by_status(temp_db, "pending")
    assert len(pending) == 1


def test_update_fetch_status_increments_failures(temp_db):
    src = UserSource(
        url="https://flaky.example/feed",
        url_hash=compute_url_hash("https://flaky.example/feed"),
        status="active", source_type="rss", normalized_config="{}",
        theme="ai", focus_areas="[]",
        llm_reasoning="", sample_json="[]", name="Flaky",
    )
    sid = insert_user_source(temp_db, src)

    update_fetch_status(temp_db, sid, "fail:timeout")
    update_fetch_status(temp_db, sid, "fail:timeout")
    got = get_by_url_hash(temp_db, src.url_hash)
    assert got.consecutive_failures == 2

    update_fetch_status(temp_db, sid, "ok")
    got = get_by_url_hash(temp_db, src.url_hash)
    assert got.consecutive_failures == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_user_sources.py -v`
Expected: FAIL (module doesn't exist).

- [ ] **Step 3: Implement `storage/user_sources.py`**

```python
"""CRUD for user_sources table."""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse, urlunparse

from storage.database import NewsDatabase

logger = logging.getLogger(__name__)


@dataclass
class UserSource:
    url: str
    url_hash: str
    status: str                      # 'pending' | 'active' | 'rejected' | 'disabled'
    source_type: str                 # 'rss' | 'youtube' | ...
    normalized_config: str           # JSON string
    theme: str                       # 'ai' | 'fashion'
    focus_areas: str                 # JSON string (list)
    llm_reasoning: str
    sample_json: str                 # JSON string (list of sample items)
    name: str
    id: Optional[int] = None
    created_at: Optional[str] = None
    activated_at: Optional[str] = None
    last_fetch_at: Optional[str] = None
    last_fetch_status: Optional[str] = None
    consecutive_failures: int = 0


def compute_url_hash(url: str) -> str:
    """Normalize URL and hash it for idempotent lookup.

    Normalization:
    - lowercase scheme + host
    - strip fragment
    - strip trailing slash on path
    """
    parsed = urlparse(url.strip())
    normalized = urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path.rstrip("/") or "/",
        parsed.params,
        parsed.query,
        "",  # strip fragment
    ))
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def insert_user_source(db: NewsDatabase, src: UserSource) -> int:
    cursor = db._conn.cursor()
    cursor.execute(
        """INSERT INTO user_sources
           (url, url_hash, status, source_type, normalized_config,
            theme, focus_areas, llm_reasoning, sample_json, name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            src.url, src.url_hash, src.status, src.source_type,
            src.normalized_config, src.theme, src.focus_areas,
            src.llm_reasoning, src.sample_json, src.name,
        ),
    )
    db._conn.commit()
    return cursor.lastrowid


def get_by_url_hash(db: NewsDatabase, url_hash: str) -> Optional[UserSource]:
    cursor = db._conn.cursor()
    cursor.execute("SELECT * FROM user_sources WHERE url_hash = ?", (url_hash,))
    row = cursor.fetchone()
    if not row:
        return None
    return _row_to_source(row)


def get_by_id(db: NewsDatabase, source_id: int) -> Optional[UserSource]:
    cursor = db._conn.cursor()
    cursor.execute("SELECT * FROM user_sources WHERE id = ?", (source_id,))
    row = cursor.fetchone()
    return _row_to_source(row) if row else None


def list_by_status(db: NewsDatabase, status: str) -> list[UserSource]:
    cursor = db._conn.cursor()
    cursor.execute(
        "SELECT * FROM user_sources WHERE status = ? ORDER BY created_at DESC",
        (status,),
    )
    return [_row_to_source(row) for row in cursor.fetchall()]


def list_all(db: NewsDatabase) -> list[UserSource]:
    cursor = db._conn.cursor()
    cursor.execute("SELECT * FROM user_sources ORDER BY created_at DESC")
    return [_row_to_source(row) for row in cursor.fetchall()]


def update_status(db: NewsDatabase, source_id: int, new_status: str) -> None:
    cursor = db._conn.cursor()
    if new_status == "active":
        cursor.execute(
            "UPDATE user_sources SET status = ?, activated_at = ? WHERE id = ?",
            (new_status, datetime.now(timezone.utc).isoformat(), source_id),
        )
    else:
        cursor.execute(
            "UPDATE user_sources SET status = ? WHERE id = ?",
            (new_status, source_id),
        )
    db._conn.commit()


def update_fields(db: NewsDatabase, source_id: int, fields: dict) -> None:
    """Update arbitrary fields on a user_source (theme, focus_areas, name)."""
    if not fields:
        return
    allowed = {"theme", "focus_areas", "name", "normalized_config"}
    clauses = []
    values = []
    for k, v in fields.items():
        if k not in allowed:
            continue
        clauses.append(f"{k} = ?")
        values.append(v)
    if not clauses:
        return
    values.append(source_id)
    cursor = db._conn.cursor()
    cursor.execute(
        f"UPDATE user_sources SET {', '.join(clauses)} WHERE id = ?",
        values,
    )
    db._conn.commit()


def update_fetch_status(db: NewsDatabase, source_id: int, status: str) -> None:
    """Update last_fetch_at + status. Reset consecutive_failures on ok, else increment."""
    cursor = db._conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    if status == "ok":
        cursor.execute(
            """UPDATE user_sources
               SET last_fetch_at = ?, last_fetch_status = ?, consecutive_failures = 0
               WHERE id = ?""",
            (now, status, source_id),
        )
    else:
        cursor.execute(
            """UPDATE user_sources
               SET last_fetch_at = ?, last_fetch_status = ?,
                   consecutive_failures = consecutive_failures + 1
               WHERE id = ?""",
            (now, status, source_id),
        )
    db._conn.commit()


def _row_to_source(row) -> UserSource:
    return UserSource(
        id=row["id"],
        url=row["url"],
        url_hash=row["url_hash"],
        status=row["status"],
        source_type=row["source_type"] or "",
        normalized_config=row["normalized_config"] or "{}",
        theme=row["theme"] or "ai",
        focus_areas=row["focus_areas"] or "[]",
        llm_reasoning=row["llm_reasoning"] or "",
        sample_json=row["sample_json"] or "[]",
        name=row["name"] or "",
        created_at=row["created_at"],
        activated_at=row["activated_at"],
        last_fetch_at=row["last_fetch_at"],
        last_fetch_status=row["last_fetch_status"],
        consecutive_failures=row["consecutive_failures"] or 0,
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_user_sources.py -v`
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add storage/user_sources.py tests/test_user_sources.py
git commit -m "feat: user_sources CRUD module with URL normalization and hash"
```

### Task 5.3: Merge dynamic sources into pipeline startup

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Add helper function to merge dynamic sources into static config**

In `main.py`, add above `build_collectors`:

```python
import json

from storage.user_sources import list_by_status, UserSource


def _merge_user_sources_into_config(config: dict, db) -> dict:
    """Merge active user_sources into a mutable copy of config['sources'].

    Each UserSource has source_type + normalized_config (JSON).
    We append its normalized_config to the matching collector's source list.
    Returns modified config.
    """
    active = list_by_status(db, "active")
    if not active:
        return config

    sources = config.setdefault("sources", {})
    count_added = 0

    for src in active:
        try:
            cfg = json.loads(src.normalized_config or "{}")
        except json.JSONDecodeError:
            logger.warning("Skipping user_source #%d: malformed config", src.id)
            continue

        # Ensure collector section exists and is enabled
        if src.source_type == "rss":
            rss = sources.setdefault("rss", {"enabled": True, "feeds": []})
            rss["enabled"] = True
            # cfg expected: {"url": ..., "name": ...}
            feed = {**cfg, "theme": src.theme, "name": src.name or cfg.get("name", src.url)}
            rss.setdefault("feeds", []).append(feed)
            count_added += 1

        elif src.source_type == "youtube":
            yt = sources.setdefault("youtube", {"enabled": True, "channels": []})
            yt["enabled"] = True
            channel = {**cfg, "theme": src.theme, "name": src.name}
            yt.setdefault("channels", []).append(channel)
            count_added += 1

        elif src.source_type == "bilibili":
            bili = sources.setdefault("bilibili", {"enabled": True, "users": []})
            bili["enabled"] = True
            user = {**cfg, "theme": src.theme, "name": src.name}
            bili.setdefault("users", []).append(user)
            count_added += 1

        elif src.source_type == "twitter":
            tw = sources.setdefault("twitter", {"enabled": True, "users": []})
            tw["enabled"] = True
            user = {**cfg, "theme": src.theme, "name": src.name}
            tw.setdefault("users", []).append(user)
            count_added += 1

        elif src.source_type == "reddit":
            rd = sources.setdefault("reddit", {"enabled": True, "subreddits": []})
            rd["enabled"] = True
            sub = {**cfg, "theme": src.theme}
            rd.setdefault("subreddits", []).append(sub)
            count_added += 1

        elif src.source_type == "telegram":
            tg = sources.setdefault("telegram", {"enabled": True, "channels": []})
            tg["enabled"] = True
            ch = {**cfg, "theme": src.theme, "name": src.name}
            tg.setdefault("channels", []).append(ch)
            count_added += 1

        else:
            logger.warning("Unknown source_type '%s' for user_source #%d", src.source_type, src.id)

    if count_added:
        logger.info("Merged %d dynamic user_sources into config", count_added)

    return config
```

- [ ] **Step 2: Call the merge in `run()` before `build_collectors`**

In `run()`, right after `db.connect()`:

```python
db.connect()
try:
    since = datetime.now(timezone.utc) - timedelta(days=args.days)

    # Merge dynamic sources from DB into config before building collectors
    config = _merge_user_sources_into_config(config, db)

    # ... rest of run() unchanged ...
```

- [ ] **Step 3: Smoke test**

Run: `python main.py --skip-ai --no-proxy --days 1 -v 2>&1 | head -40`
Expected:
- No errors
- If user_sources table is empty: no "Merged X dynamic sources" log line
- Pipeline runs normally with static config sources

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: main.py merges active user_sources into collector config at startup"
```

---

## Phase 6 — Subscription Analyzer Backend Module

The new `processor/subscribe_analyzer.py` module: URL detector + sample fetch + LLM analysis.

### Task 6.1: URL detector — pure function chain

**Files:**
- Create: `processor/subscribe_analyzer.py` (initial skeleton with detectors only)
- Create: `tests/test_subscribe_analyzer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_subscribe_analyzer.py`:

```python
"""Tests for subscribe_analyzer URL detector."""

import pytest

from processor.subscribe_analyzer import detect_url_type, DetectionResult


def test_detect_youtube_channel_url():
    r = detect_url_type("https://www.youtube.com/channel/UCbfYPyITQ-7l4upoX8nvctg", rsshub_routes=[])
    assert r.type == "youtube"
    assert r.config["channel_id"] == "UCbfYPyITQ-7l4upoX8nvctg"


def test_detect_youtube_handle_url():
    r = detect_url_type("https://youtube.com/@mkbhd", rsshub_routes=[])
    assert r.type == "youtube"
    assert r.config["handle"] == "mkbhd"


def test_detect_bilibili_space():
    r = detect_url_type("https://space.bilibili.com/291229", rsshub_routes=[])
    assert r.type == "bilibili"
    assert r.config["uid"] == "291229"


def test_detect_twitter_profile():
    r = detect_url_type("https://twitter.com/karpathy", rsshub_routes=[])
    assert r.type == "twitter"
    assert r.config["handle"] == "karpathy"


def test_detect_x_com_profile():
    r = detect_url_type("https://x.com/sama", rsshub_routes=[])
    assert r.type == "twitter"
    assert r.config["handle"] == "sama"


def test_detect_reddit_subreddit():
    r = detect_url_type("https://reddit.com/r/MachineLearning", rsshub_routes=[])
    assert r.type == "reddit"
    assert r.config["subreddit"] == "MachineLearning"


def test_detect_telegram_channel():
    r = detect_url_type("https://t.me/zaihuapd", rsshub_routes=[])
    assert r.type == "telegram"
    assert r.config["channel"] == "zaihuapd"


def test_detect_github_repo():
    r = detect_url_type("https://github.com/anthropics/claude-code", rsshub_routes=[])
    assert r.type == "github"
    assert r.config["owner"] == "anthropics"
    assert r.config["repo"] == "claude-code"


def test_detect_rsshub_route_xiaohongshu():
    routes = [
        {"pattern": r"xiaohongshu\.com/user/profile/(\w+)",
         "template": "/xiaohongshu/user/{1}"},
    ]
    r = detect_url_type(
        "https://www.xiaohongshu.com/user/profile/abc123",
        rsshub_routes=routes,
        rsshub_base_url="http://rsshub.local:1200",
    )
    assert r.type == "rss"
    assert r.config["feed_url"] == "http://rsshub.local:1200/xiaohongshu/user/abc123"


def test_detect_rsshub_route_weibo():
    routes = [
        {"pattern": r"weibo\.com/u/(\d+)", "template": "/weibo/user/{1}"},
    ]
    r = detect_url_type(
        "https://weibo.com/u/123456",
        rsshub_routes=routes,
        rsshub_base_url="http://rsshub.local:1200",
    )
    assert r.type == "rss"
    assert r.config["feed_url"] == "http://rsshub.local:1200/weibo/user/123456"


def test_detect_unknown_returns_unknown_type():
    r = detect_url_type("https://random.example.com/page", rsshub_routes=[])
    # Unknown type — caller will try direct RSS probing separately
    assert r.type == "unknown"


def test_detect_handles_trailing_slash_and_www():
    r1 = detect_url_type("https://www.youtube.com/channel/UC123/", rsshub_routes=[])
    r2 = detect_url_type("https://youtube.com/channel/UC123", rsshub_routes=[])
    assert r1.type == r2.type == "youtube"
    assert r1.config["channel_id"] == r2.config["channel_id"] == "UC123"


def test_detect_x_com_is_not_confused_by_status_url():
    # tweet URL, not profile — should not match as subscribe-able
    r = detect_url_type("https://x.com/karpathy/status/12345", rsshub_routes=[])
    # Our simple heuristic matches profile form; status URL still looks like handle "karpathy"
    # followed by extra path. Accept this as twitter with handle=karpathy (approximation OK).
    # If strict mode wanted later, detector can be tightened.
    assert r.type in ("twitter", "unknown")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_subscribe_analyzer.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement detector**

Create `processor/subscribe_analyzer.py` initial skeleton with detectors (later tasks extend it):

```python
"""Subscription analyzer: URL type detection + sample fetch + LLM judgment."""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    type: str                                  # 'rss' | 'youtube' | 'twitter' | 'bilibili' | 'reddit' | 'telegram' | 'github' | 'unknown'
    config: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None                # populated when type='unknown'


def detect_url_type(
    url: str,
    rsshub_routes: list[dict],
    rsshub_base_url: str = "",
) -> DetectionResult:
    """Run detector chain from most-specific to most-generic. First match wins.

    This covers ALL detectors that can be determined from the URL alone.
    Direct-RSS probing and HTML autodiscovery require HTTP — call
    probe_rss_feed(url) separately when detect_url_type returns 'unknown'.
    """
    # Strip fragment, normalize
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower().lstrip("www.")
    path = parsed.path.rstrip("/")

    # 1) YouTube
    if host in ("youtube.com", "m.youtube.com"):
        m = re.match(r"^/channel/(UC[\w-]+)", path)
        if m:
            return DetectionResult("youtube", {"channel_id": m.group(1)})
        m = re.match(r"^/@([\w.-]+)", path)
        if m:
            return DetectionResult("youtube", {"handle": m.group(1)})

    # 2) Bilibili space
    if host == "space.bilibili.com":
        m = re.match(r"^/(\d+)", path)
        if m:
            return DetectionResult("bilibili", {"uid": m.group(1)})

    # 3) Twitter / X
    if host in ("twitter.com", "x.com"):
        m = re.match(r"^/([\w_]+)$", path) or re.match(r"^/([\w_]+)/status/", path)
        if m:
            return DetectionResult("twitter", {"handle": m.group(1)})

    # 4) Reddit subreddit
    if host == "reddit.com" or host.endswith(".reddit.com"):
        m = re.match(r"^/r/([\w_]+)", path)
        if m:
            return DetectionResult("reddit", {"subreddit": m.group(1)})

    # 5) Telegram
    if host == "t.me":
        m = re.match(r"^/([\w_]+)", path)
        if m:
            return DetectionResult("telegram", {"channel": m.group(1)})

    # 6) GitHub repo
    if host == "github.com":
        m = re.match(r"^/([\w.-]+)/([\w.-]+)", path)
        if m:
            return DetectionResult("github", {"owner": m.group(1), "repo": m.group(2)})

    # 7) RSSHub routes (full URL match including host)
    for route in rsshub_routes or []:
        pattern = route.get("pattern", "")
        template = route.get("template", "")
        if not pattern or not template:
            continue
        full_url = f"{parsed.hostname or ''}{parsed.path}"
        m = re.search(pattern, full_url)
        if m:
            feed_url = _fill_template(template, m)
            if rsshub_base_url:
                feed_url = rsshub_base_url.rstrip("/") + feed_url
            return DetectionResult("rss", {"feed_url": feed_url, "name": url})

    # 8) Fallback: unknown (caller may try probe_rss_feed next)
    return DetectionResult("unknown", error="No detector matched URL")


def _fill_template(template: str, match: re.Match) -> str:
    """Replace {1}, {2}, ... in template with match groups."""
    result = template
    for i, group in enumerate(match.groups(), start=1):
        result = result.replace(f"{{{i}}}", group)
    return result
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_subscribe_analyzer.py -v`
Expected: 12+ tests pass. (The last `x.com/status/...` test is lenient — either outcome OK.)

- [ ] **Step 5: Commit**

```bash
git add processor/subscribe_analyzer.py tests/test_subscribe_analyzer.py
git commit -m "feat: URL type detector chain for subscribe_analyzer"
```

### Task 6.2: RSS probing (direct + HTML autodiscovery)

**Files:**
- Modify: `processor/subscribe_analyzer.py`
- Modify: `tests/test_subscribe_analyzer.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_subscribe_analyzer.py`:

```python
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_probe_rss_direct_xml_response():
    from processor.subscribe_analyzer import probe_rss_feed

    client = AsyncMock()
    response = MagicMock()
    response.headers = {"content-type": "application/rss+xml; charset=utf-8"}
    response.text = "<rss></rss>"
    response.status_code = 200
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    r = await probe_rss_feed("https://example.com/feed", client)
    assert r.type == "rss"
    assert r.config["feed_url"] == "https://example.com/feed"


@pytest.mark.asyncio
async def test_probe_rss_html_autodiscovery():
    from processor.subscribe_analyzer import probe_rss_feed

    html = """
    <html><head>
      <link rel="alternate" type="application/rss+xml" href="/feed.xml">
    </head><body>...</body></html>
    """
    client = AsyncMock()
    response = MagicMock()
    response.headers = {"content-type": "text/html"}
    response.text = html
    response.status_code = 200
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    r = await probe_rss_feed("https://example.com/", client)
    assert r.type == "rss"
    assert r.config["feed_url"] == "https://example.com/feed.xml"


@pytest.mark.asyncio
async def test_probe_rss_returns_unknown_on_plain_html():
    from processor.subscribe_analyzer import probe_rss_feed

    client = AsyncMock()
    response = MagicMock()
    response.headers = {"content-type": "text/html"}
    response.text = "<html><body>No feed here</body></html>"
    response.status_code = 200
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    r = await probe_rss_feed("https://example.com/", client)
    assert r.type == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_subscribe_analyzer.py -v`
Expected: New tests FAIL (probe_rss_feed not defined).

- [ ] **Step 3: Implement `probe_rss_feed`**

Add to `processor/subscribe_analyzer.py`:

```python
import httpx
from urllib.parse import urljoin


async def probe_rss_feed(url: str, client: httpx.AsyncClient) -> DetectionResult:
    """HTTP-dependent fallback probe for RSS: try direct fetch + HTML autodiscovery."""
    try:
        response = await client.get(url, follow_redirects=True, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as e:
        return DetectionResult("unknown", error=f"HTTP error: {e}")
    except Exception as e:
        return DetectionResult("unknown", error=f"Fetch failed: {e}")

    ctype = (response.headers.get("content-type") or "").lower()
    body = response.text

    # Direct RSS: content-type indicates feed
    if any(t in ctype for t in ("application/rss", "application/atom", "text/xml", "application/xml")):
        return DetectionResult("rss", {"feed_url": url, "name": url})

    # Body starts with <rss or <feed — another direct hint
    stripped = body.lstrip()[:200].lower()
    if stripped.startswith(("<?xml", "<rss", "<feed")):
        return DetectionResult("rss", {"feed_url": url, "name": url})

    # HTML autodiscovery
    m = re.search(
        r'<link[^>]+rel=["\']alternate["\'][^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>',
        body, flags=re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]+rel=["\']alternate["\'][^>]*>',
            body, flags=re.IGNORECASE,
        )
    if m:
        link_tag = m.group(0)
        href_m = re.search(r'href=["\']([^"\']+)["\']', link_tag, flags=re.IGNORECASE)
        if href_m:
            feed_url = urljoin(url, href_m.group(1))
            return DetectionResult("rss", {"feed_url": feed_url, "name": url})

    return DetectionResult("unknown", error="No feed detected in page")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_subscribe_analyzer.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add processor/subscribe_analyzer.py tests/test_subscribe_analyzer.py
git commit -m "feat: add probe_rss_feed for direct + HTML autodiscovery"
```

### Task 6.3: Sample fetcher — reuse RSS collector

**Files:**
- Modify: `processor/subscribe_analyzer.py`
- Modify: `tests/test_subscribe_analyzer.py`

For v1 we only need RSS sample fetching (all non-RSS detected types ultimately also map to RSS via existing collectors or RSSHub). Keep this minimal.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_subscribe_analyzer.py`:

```python
@pytest.mark.asyncio
async def test_fetch_sample_rss_returns_up_to_n_items():
    from processor.subscribe_analyzer import fetch_sample

    rss_body = """<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item><title>Item 1</title><link>https://example.com/1</link><pubDate>Mon, 21 Apr 2026 10:00:00 +0000</pubDate></item>
      <item><title>Item 2</title><link>https://example.com/2</link><pubDate>Mon, 21 Apr 2026 11:00:00 +0000</pubDate></item>
      <item><title>Item 3</title><link>https://example.com/3</link><pubDate>Mon, 21 Apr 2026 12:00:00 +0000</pubDate></item>
    </channel></rss>"""

    client = AsyncMock()
    response = MagicMock()
    response.text = rss_body
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    detection = DetectionResult("rss", {"feed_url": "https://example.com/feed"})
    samples = await fetch_sample(detection, client, n=2)
    assert len(samples) == 2
    assert samples[0]["title"] == "Item 1"
```

- [ ] **Step 2: Implement `fetch_sample`**

Add to `processor/subscribe_analyzer.py`:

```python
from datetime import datetime, timezone

import feedparser


async def fetch_sample(
    detection: DetectionResult,
    client: httpx.AsyncClient,
    n: int = 5,
) -> list[dict]:
    """Fetch up to N most recent items from the detected source.

    Returns list of dicts: {title, url, published_at (iso or None), snippet}.
    Empty list if fetch fails.
    """
    if detection.type == "rss":
        return await _sample_rss(detection.config["feed_url"], client, n)

    # For non-RSS types, v1 constructs an RSSHub URL as feed
    if detection.type in ("youtube", "bilibili", "twitter", "reddit", "telegram"):
        # Caller is expected to have resolved an RSSHub route first for non-Western types,
        # or the existing collectors will handle during pipeline run. For sample fetching,
        # we return empty and let the LLM judge from URL alone if no sample available.
        logger.info(
            "Sample fetch skipped for type %s (no ad-hoc non-RSS sampler in v1)",
            detection.type,
        )
        return []

    return []


async def _sample_rss(feed_url: str, client: httpx.AsyncClient, n: int) -> list[dict]:
    try:
        response = await client.get(feed_url, follow_redirects=True, timeout=10.0)
        response.raise_for_status()
    except Exception as e:
        logger.warning("Sample RSS fetch failed for %s: %s", feed_url, e)
        return []

    feed = feedparser.parse(response.text)
    samples = []
    for entry in feed.entries[:n]:
        published = entry.get("published") or entry.get("updated") or ""
        snippet = entry.get("summary") or entry.get("description") or ""
        # Strip HTML tags crudely for LLM input
        snippet = re.sub(r"<[^>]+>", "", snippet)[:400]
        samples.append({
            "title": entry.get("title", "Untitled"),
            "url": entry.get("link", ""),
            "published_at": published,
            "snippet": snippet,
        })
    return samples
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_subscribe_analyzer.py -v`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add processor/subscribe_analyzer.py tests/test_subscribe_analyzer.py
git commit -m "feat: fetch_sample for RSS feeds (up to N recent items)"
```

### Task 6.4: LLM analysis + orchestration

**Files:**
- Modify: `processor/subscribe_analyzer.py`
- Modify: `tests/test_subscribe_analyzer.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_subscribe_analyzer.py`:

```python
@pytest.mark.asyncio
async def test_analyze_url_happy_path(monkeypatch):
    """End-to-end analyze: detect → sample (mocked) → LLM (mocked) → result."""
    from processor import subscribe_analyzer

    # Mock probe and sample paths to return a controlled RSS detection
    async def fake_fetch_sample(detection, client, n=5):
        return [
            {"title": "Hypebeast drop", "url": "u1", "published_at": "", "snippet": "sneaker release"},
            {"title": "Supreme FW26", "url": "u2", "published_at": "", "snippet": "new collection"},
        ]

    async def fake_llm(prompt, cfg, client):
        return {
            "theme": "fashion",
            "suggested_focus_areas": ["潮流"],
            "quality_score": 8,
            "verdict": "accept",
            "reasoning": "High-quality streetwear feed.",
        }

    monkeypatch.setattr(subscribe_analyzer, "fetch_sample", fake_fetch_sample)
    monkeypatch.setattr(subscribe_analyzer, "_call_llm", fake_llm)

    client = AsyncMock()
    cfg = {
        "rsshub": {"base_url": "", "routes": []},
        "subscribe_analyzer": {
            "prompt_template": "Analyze: {samples}",
            "llm": {"model": "m", "api_key": "k", "base_url": "u"},
        },
    }

    result = await subscribe_analyzer.analyze_url(
        "https://hypebeast.com/feed", cfg, client,
    )

    assert result["detected_type"] == "rss"
    assert result["llm"]["theme"] == "fashion"
    assert result["llm"]["verdict"] == "accept"
    assert len(result["sample"]) == 2


@pytest.mark.asyncio
async def test_analyze_url_llm_failure_returns_manual_review(monkeypatch):
    from processor import subscribe_analyzer

    async def fake_fetch_sample(detection, client, n=5):
        return [{"title": "T", "url": "u", "published_at": "", "snippet": "s"}]

    async def fake_llm_fail(prompt, cfg, client):
        raise ValueError("LLM broke")

    monkeypatch.setattr(subscribe_analyzer, "fetch_sample", fake_fetch_sample)
    monkeypatch.setattr(subscribe_analyzer, "_call_llm", fake_llm_fail)

    client = AsyncMock()
    cfg = {
        "rsshub": {"base_url": "", "routes": []},
        "subscribe_analyzer": {"prompt_template": "x", "llm": {}},
    }

    result = await subscribe_analyzer.analyze_url(
        "https://hypebeast.com/feed", cfg, client,
    )
    assert result["llm"]["verdict"] == "manual_review"
    assert "failed" in result["llm"]["reasoning"].lower() or "不可用" in result["llm"]["reasoning"]
```

- [ ] **Step 2: Implement `analyze_url` + `_call_llm`**

Append to `processor/subscribe_analyzer.py`:

```python
import json


async def analyze_url(
    url: str,
    config: dict,
    client: httpx.AsyncClient,
) -> dict:
    """Orchestrate: detect → probe RSS if unknown → sample → LLM analyze.

    Returns a dict shaped like the /api/subscribe/analyze response (no DB writes).
    Caller is responsible for caching and persistence.
    """
    rsshub_cfg = config.get("rsshub", {})
    routes = rsshub_cfg.get("routes", [])
    rsshub_base = rsshub_cfg.get("base_url", "")

    detection = detect_url_type(url, rsshub_routes=routes, rsshub_base_url=rsshub_base)

    # If URL didn't match any specific pattern, try HTTP probing for RSS
    if detection.type == "unknown":
        detection = await probe_rss_feed(url, client)

    # If still unknown, return without LLM call
    if detection.type == "unknown":
        return {
            "detected_type": "unknown",
            "sample": [],
            "llm": {
                "theme": "neither",
                "suggested_focus_areas": [],
                "quality_score": 0,
                "verdict": "reject",
                "reasoning": detection.error or "无法识别此 URL 的订阅类型",
            },
            "normalized_config": {},
        }

    # Fetch sample
    sample = await fetch_sample(detection, client, n=5)

    # LLM analyze
    sa_cfg = config.get("subscribe_analyzer", {})
    try:
        llm_result = await _call_llm(
            _build_prompt(sa_cfg.get("prompt_template", DEFAULT_PROMPT_TEMPLATE), sample),
            sa_cfg.get("llm", config.get("llm", {})),
            client,
        )
    except Exception as e:
        logger.warning("LLM subscription analysis failed: %s", e)
        # Retry once
        try:
            llm_result = await _call_llm(
                _build_prompt(sa_cfg.get("prompt_template", DEFAULT_PROMPT_TEMPLATE), sample),
                sa_cfg.get("llm", config.get("llm", {})),
                client,
            )
        except Exception as e2:
            logger.warning("LLM retry failed: %s", e2)
            llm_result = {
                "theme": "neither",
                "suggested_focus_areas": [],
                "quality_score": 0,
                "verdict": "manual_review",
                "reasoning": "AI 分析暂时不可用，请根据样本自行判断 (LLM failed)",
            }

    return {
        "detected_type": detection.type,
        "sample": sample,
        "llm": llm_result,
        "normalized_config": detection.config,
    }


DEFAULT_PROMPT_TEMPLATE = """你是订阅分析助手。判断以下源是否值得订阅到"AI + 时尚"聚合系统。

可选主题与 focus_area：
- ai: [开源模型, ComfyUI, 商用产品, Agent & Skills, 3D生成与重建, 训练与部署]
- fashion: [潮流, 时装, AI × 时尚]

样本（最近 {n} 条）：
{samples}

请以 JSON 返回（不要加 markdown 代码块）：
{{
  "theme": "ai" | "fashion" | "neither",
  "suggested_focus_areas": ["..."],
  "quality_score": 0-10,
  "verdict": "accept" | "reject" | "manual_review",
  "reasoning": "2-3 句说明"
}}

评分参考:
- 更新频率高、内容深度、原创性 → 加分
- 纯带货/营销、内容低质、与两个主题都无关 → 减分
- verdict: >=6 accept, <4 reject, 4-5.9 manual_review
"""


def _build_prompt(template: str, samples: list[dict]) -> str:
    if not samples:
        sample_text = "(无法抓取样本，请仅基于 URL 本身判断)"
    else:
        lines = []
        for i, s in enumerate(samples, 1):
            lines.append(f"{i}. {s['title']}\n   {s.get('snippet', '')[:200]}")
        sample_text = "\n".join(lines)
    return template.replace("{n}", str(len(samples))).replace("{samples}", sample_text)


async def _call_llm(prompt: str, llm_cfg: dict, client: httpx.AsyncClient) -> dict:
    api_key = llm_cfg.get("api_key", "")
    base_url = llm_cfg.get("base_url", "https://api.openai.com/v1")
    model = llm_cfg.get("model", "gpt-4o-mini")
    temperature = llm_cfg.get("temperature", 0.2)

    if not api_key:
        raise ValueError("LLM api_key not configured for subscribe_analyzer")

    resp = await client.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a subscription analysis assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": 512,
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"].strip()

    # Strip code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) >= 3 else text.strip("`")

    return json.loads(text)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_subscribe_analyzer.py -v`
Expected: all tests pass (including the two new end-to-end ones).

- [ ] **Step 4: Commit**

```bash
git add processor/subscribe_analyzer.py tests/test_subscribe_analyzer.py
git commit -m "feat: analyze_url orchestrator with LLM + retry + manual_review fallback"
```

### Task 6.5: Add subscribe_analyzer + rsshub config blocks

**Files:**
- Modify: `config.yaml`

- [ ] **Step 1: Add `rsshub` block at top level**

```yaml
rsshub:
  base_url: "${RSSHUB_URL}"     # e.g., http://localhost:1200 (set in .env)
  routes:
    - { pattern: "xiaohongshu\\.com/user/profile/(\\w+)", template: "/xiaohongshu/user/{1}" }
    - { pattern: "weibo\\.com/u/(\\d+)",                  template: "/weibo/user/{1}" }
    - { pattern: "space\\.bilibili\\.com/(\\d+)",         template: "/bilibili/user/video/{1}" }
```

- [ ] **Step 2: Add `subscribe_analyzer` block**

```yaml
subscribe_analyzer:
  llm:
    # Defaults to top-level llm.* if omitted; override here for cost tuning.
    model: "claude-sonnet-4-6"
    temperature: 0.2
  # Optional: override the default prompt if you want a different judgment style.
  # prompt_template: |
  #   ...your template with {n} and {samples} placeholders...
```

- [ ] **Step 3: Add `RSSHUB_URL` to `.env.example`** (create if missing)

```bash
# .env.example
RSSHUB_URL=http://localhost:1200
```

(Do not commit `.env` — just the example.)

- [ ] **Step 4: Smoke test config loads**

Run: `python -c "import yaml; c = yaml.safe_load(open('config.yaml')); print(c.get('rsshub')); print(c.get('subscribe_analyzer'))"`
Expected: both dicts printed, no errors.

- [ ] **Step 5: Commit**

```bash
git add config.yaml .env.example
git commit -m "config: add rsshub routes and subscribe_analyzer LLM block"
```

---

## Phase 7 — Subscribe API Routes

Expose the analyzer and CRUD as FastAPI endpoints.

### Task 7.1: Subscribe router skeleton + /analyze + /confirm

**Files:**
- Create: `web/routers/__init__.py`
- Create: `web/routers/subscribe.py`
- Modify: `web/app.py`

- [ ] **Step 1: Create `web/routers/__init__.py`** (empty file for package)

- [ ] **Step 2: Create `web/routers/subscribe.py`**

```python
"""Subscribe API: analyze URLs and manage user_sources."""

import json
import logging
import os
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from processor.subscribe_analyzer import analyze_url
from storage.database import NewsDatabase
from storage.user_sources import (
    UserSource, compute_url_hash, get_by_id, get_by_url_hash,
    insert_user_source, list_by_status, list_all, update_fields,
    update_status,
)

logger = logging.getLogger(__name__)
load_dotenv()

router = APIRouter(prefix="/api/subscribe", tags=["subscribe"])

DB_PATH = os.getenv("NEWS_DB_PATH", "./data/news.db")


def _load_config_for_analyzer() -> dict:
    """Load config.yaml for analyzer (re-reads each request — simple but OK for v1)."""
    import re
    import yaml

    with open("config.yaml", "r", encoding="utf-8") as f:
        raw = f.read()

    def replace_env(match):
        return os.getenv(match.group(1), match.group(0))

    resolved = re.sub(r"\$\{(\w+)\}", replace_env, raw)
    return yaml.safe_load(resolved)


def _get_db() -> NewsDatabase:
    db = NewsDatabase(DB_PATH)
    db.connect()
    return db


class AnalyzeRequest(BaseModel):
    url: str


class AnalyzeResponse(BaseModel):
    analysis_id: int
    url_hash: str
    detected_type: str
    sample: list[dict]
    llm: dict
    cached: bool = False
    already_subscribed: bool = False
    previously_rejected: bool = False


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    url_hash = compute_url_hash(url)
    db = _get_db()

    try:
        existing = get_by_url_hash(db, url_hash)

        if existing and existing.status == "active":
            return AnalyzeResponse(
                analysis_id=existing.id,
                url_hash=url_hash,
                detected_type=existing.source_type or "rss",
                sample=json.loads(existing.sample_json or "[]"),
                llm={
                    "theme": existing.theme,
                    "suggested_focus_areas": json.loads(existing.focus_areas or "[]"),
                    "quality_score": 0,
                    "verdict": "accept",
                    "reasoning": existing.llm_reasoning,
                },
                cached=True,
                already_subscribed=True,
            )

        if existing and existing.status == "pending":
            # Return cached pending analysis
            return AnalyzeResponse(
                analysis_id=existing.id,
                url_hash=url_hash,
                detected_type=existing.source_type or "unknown",
                sample=json.loads(existing.sample_json or "[]"),
                llm={
                    "theme": existing.theme,
                    "suggested_focus_areas": json.loads(existing.focus_areas or "[]"),
                    "quality_score": 0,
                    "verdict": "accept" if existing.theme in ("ai", "fashion") else "manual_review",
                    "reasoning": existing.llm_reasoning,
                },
                cached=True,
            )

        if existing and existing.status == "rejected":
            return AnalyzeResponse(
                analysis_id=existing.id,
                url_hash=url_hash,
                detected_type=existing.source_type or "unknown",
                sample=json.loads(existing.sample_json or "[]"),
                llm={
                    "theme": existing.theme or "neither",
                    "suggested_focus_areas": [],
                    "quality_score": 0,
                    "verdict": "reject",
                    "reasoning": existing.llm_reasoning,
                },
                cached=True,
                previously_rejected=True,
            )

        # Fresh analysis
        cfg = _load_config_for_analyzer()
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=True) as client:
            result = await analyze_url(url, cfg, client)

        # Persist as pending
        src = UserSource(
            url=url,
            url_hash=url_hash,
            status="pending",
            source_type=result["detected_type"],
            normalized_config=json.dumps(result.get("normalized_config", {})),
            theme=result["llm"].get("theme", "ai"),
            focus_areas=json.dumps(result["llm"].get("suggested_focus_areas", [])),
            llm_reasoning=result["llm"].get("reasoning", ""),
            sample_json=json.dumps(result["sample"]),
            name="",  # user supplies on confirm
        )
        analysis_id = insert_user_source(db, src)

        return AnalyzeResponse(
            analysis_id=analysis_id,
            url_hash=url_hash,
            detected_type=result["detected_type"],
            sample=result["sample"],
            llm=result["llm"],
        )
    finally:
        db.close()


class ConfirmOverrides(BaseModel):
    theme: Optional[str] = None
    focus_areas: Optional[list[str]] = None
    name: Optional[str] = None


class ConfirmRequest(BaseModel):
    analysis_id: int
    action: str                     # 'accept' | 'reject'
    overrides: Optional[ConfirmOverrides] = None


class ConfirmResponse(BaseModel):
    status: str
    source_id: int


@router.post("/confirm", response_model=ConfirmResponse)
async def confirm(req: ConfirmRequest):
    if req.action not in ("accept", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'accept' or 'reject'")

    db = _get_db()
    try:
        src = get_by_id(db, req.analysis_id)
        if not src:
            raise HTTPException(status_code=404, detail="Analysis not found")

        if req.action == "reject":
            update_status(db, req.analysis_id, "rejected")
            return ConfirmResponse(status="rejected", source_id=req.analysis_id)

        # Apply overrides
        fields = {}
        if req.overrides:
            if req.overrides.theme:
                fields["theme"] = req.overrides.theme
            if req.overrides.focus_areas is not None:
                fields["focus_areas"] = json.dumps(req.overrides.focus_areas)
            if req.overrides.name:
                fields["name"] = req.overrides.name
        if fields:
            update_fields(db, req.analysis_id, fields)

        update_status(db, req.analysis_id, "active")
        return ConfirmResponse(status="active", source_id=req.analysis_id)
    finally:
        db.close()
```

- [ ] **Step 3: Register router in `web/app.py`**

Add near the bottom of `web/app.py` (before `register_ai_routes`):

```python
from web.routers.subscribe import router as subscribe_router
app.include_router(subscribe_router)
```

- [ ] **Step 4: Smoke test — start server and hit endpoint**

In terminal 1:
Run: `python main.py --serve --port 8800`

In terminal 2:
Run:
```bash
curl -X POST http://localhost:8800/api/subscribe/analyze \
  -H "Content-Type: application/json" \
  -d '{"url":"https://this-is-definitely-not-a-real-url-xyz.example/feed"}'
```

Expected: HTTP 200 with `detected_type: "unknown"` and `verdict: "reject"` (or 400 if URL malformed). No crash.

- [ ] **Step 5: Commit**

```bash
git add web/routers/ web/app.py
git commit -m "feat: POST /api/subscribe/analyze and /confirm endpoints"
```

### Task 7.2: Subscribe list + delete + patch endpoints

**Files:**
- Modify: `web/routers/subscribe.py`

- [ ] **Step 1: Add list + delete + patch endpoints**

Append to `web/routers/subscribe.py`:

```python
class SubscriptionSummary(BaseModel):
    id: int
    url: str
    name: str
    source_type: str
    theme: str
    focus_areas: list[str]
    status: str
    created_at: Optional[str]
    activated_at: Optional[str]
    last_fetch_at: Optional[str]
    last_fetch_status: Optional[str]
    consecutive_failures: int


def _to_summary(src: UserSource) -> SubscriptionSummary:
    try:
        focus = json.loads(src.focus_areas or "[]")
    except json.JSONDecodeError:
        focus = []
    return SubscriptionSummary(
        id=src.id,
        url=src.url,
        name=src.name,
        source_type=src.source_type,
        theme=src.theme,
        focus_areas=focus,
        status=src.status,
        created_at=src.created_at,
        activated_at=src.activated_at,
        last_fetch_at=src.last_fetch_at,
        last_fetch_status=src.last_fetch_status,
        consecutive_failures=src.consecutive_failures,
    )


@router.get("/list", response_model=list[SubscriptionSummary])
def list_subscriptions(status: Optional[str] = Query(None)):
    db = _get_db()
    try:
        if status:
            return [_to_summary(s) for s in list_by_status(db, status)]
        return [_to_summary(s) for s in list_all(db)]
    finally:
        db.close()


@router.delete("/{source_id}")
def delete_subscription(source_id: int):
    """Soft-delete: mark as rejected. Preserves history / prevents re-analysis."""
    db = _get_db()
    try:
        src = get_by_id(db, source_id)
        if not src:
            raise HTTPException(status_code=404, detail="Not found")
        update_status(db, source_id, "rejected")
        return {"status": "rejected", "source_id": source_id}
    finally:
        db.close()


class PatchSubscription(BaseModel):
    status: Optional[str] = None            # 'active' | 'disabled' | 'rejected'
    theme: Optional[str] = None
    focus_areas: Optional[list[str]] = None
    name: Optional[str] = None


@router.patch("/{source_id}", response_model=SubscriptionSummary)
def patch_subscription(source_id: int, patch: PatchSubscription):
    db = _get_db()
    try:
        src = get_by_id(db, source_id)
        if not src:
            raise HTTPException(status_code=404, detail="Not found")

        fields = {}
        if patch.theme:
            fields["theme"] = patch.theme
        if patch.focus_areas is not None:
            fields["focus_areas"] = json.dumps(patch.focus_areas)
        if patch.name is not None:
            fields["name"] = patch.name
        if fields:
            update_fields(db, source_id, fields)

        if patch.status:
            if patch.status not in ("pending", "active", "rejected", "disabled"):
                raise HTTPException(status_code=400, detail="Invalid status")
            update_status(db, source_id, patch.status)

        updated = get_by_id(db, source_id)
        return _to_summary(updated)
    finally:
        db.close()
```

- [ ] **Step 2: Smoke test — list empty**

With server running:

Run:
```bash
curl http://localhost:8800/api/subscribe/list
```

Expected: `[]` (empty array).

- [ ] **Step 3: Commit**

```bash
git add web/routers/subscribe.py
git commit -m "feat: /api/subscribe/list, DELETE, PATCH endpoints"
```

### Task 7.3: Add theme filter to /api/news

**Files:**
- Modify: `web/app.py`
- Modify: `storage/database.py`

- [ ] **Step 1: Add `theme` parameter to `search_items` in database.py**

In `storage/database.py`, modify `search_items` signature and body:

```python
def search_items(
    self,
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    source: str | None = None,
    category: str | None = None,
    theme: str | None = None,        # NEW
    q: str | None = None,
    min_score: float | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[ContentItem], int]:
    # ... existing condition building ...

    if theme:
        conditions.append("theme = ?")
        params.append(theme)

    # ... rest unchanged ...
```

- [ ] **Step 2: Add `theme` parameter to `/api/news` endpoint**

In `web/app.py`, modify `list_news`:

```python
@app.get("/api/news", response_model=PaginatedNews)
def list_news(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    theme: Optional[str] = Query(None, description="ai | fashion"),   # NEW
    q: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    db = _get_db()
    try:
        items, total = db.search_items(
            date=date, date_from=date_from, date_to=date_to,
            source=source, category=category, theme=theme,
            q=q, min_score=min_score, page=page, page_size=page_size,
        )
        pages = (total + page_size - 1) // page_size if total else 0
        return PaginatedNews(
            items=[_item_to_resp(i) for i in items],
            total=total, page=page, page_size=page_size, pages=pages,
        )
    finally:
        db.close()
```

- [ ] **Step 3: Add theme to the response model**

In `NewsItemResponse` add:

```python
class NewsItemResponse(BaseModel):
    id: str
    source_type: str
    title: str
    url: str
    content: str
    author: str
    published_at: Optional[str]
    collected_at: str
    ai_score: Optional[float]
    ai_summary: Optional[str]
    ai_categories: list[str]
    ai_tags: list[str]
    theme: str = "ai"       # NEW
```

And update `_item_to_resp`:

```python
def _item_to_resp(item) -> NewsItemResponse:
    return NewsItemResponse(
        # ... existing fields ...
        theme=item.theme.value if hasattr(item.theme, "value") else str(item.theme),
    )
```

- [ ] **Step 4: Smoke test**

Run (server still running):
```bash
curl "http://localhost:8800/api/news?theme=fashion&page_size=5"
```
Expected: HTTP 200 JSON (possibly empty items list; no server error).

```bash
curl "http://localhost:8800/api/news?theme=ai&page_size=5"
```
Expected: HTTP 200 with items (if any exist for today).

- [ ] **Step 5: Commit**

```bash
git add storage/database.py web/app.py
git commit -m "feat: add theme filter to /api/news and expose theme in response"
```

---

## Phase 8 — Frontend: Theme Tabs

Add a tab switcher above the existing content grid.

### Task 8.1: Theme tab markup + basic styling

**Files:**
- Modify: `web/static/index.html`
- Modify: `web/static/style.css`

- [ ] **Step 1: Add theme tab markup**

In `web/static/index.html`, locate the header / filter area and add above the existing focus_area filters:

```html
<div class="theme-tabs" role="tablist" aria-label="Theme switcher">
  <button class="theme-tab active" data-theme="ai" role="tab" aria-selected="true">
    🤖 AI
  </button>
  <button class="theme-tab" data-theme="fashion" role="tab" aria-selected="false">
    👗 时尚
  </button>
</div>

<div class="header-actions">
  <button id="btn-add-subscribe" class="btn-primary">+ 添加订阅</button>
  <a href="/subscribe.html" class="btn-secondary">订阅管理</a>
</div>
```

- [ ] **Step 2: Add CSS for tabs**

Append to `web/static/style.css`:

```css
.theme-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  border-bottom: 2px solid var(--border, #333);
}

.theme-tab {
  padding: 10px 20px;
  background: transparent;
  border: none;
  border-bottom: 3px solid transparent;
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  color: var(--text-muted, #888);
  transition: color 0.15s, border-color 0.15s;
}

.theme-tab:hover {
  color: var(--text, #eee);
}

.theme-tab.active {
  color: var(--text, #eee);
  border-bottom-color: var(--accent, #4a9eff);
}

.header-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.btn-primary, .btn-secondary {
  padding: 8px 16px;
  border: 1px solid var(--accent, #4a9eff);
  border-radius: 4px;
  background: var(--accent, #4a9eff);
  color: white;
  font-size: 0.9rem;
  text-decoration: none;
  cursor: pointer;
}

.btn-secondary {
  background: transparent;
  color: var(--accent, #4a9eff);
}
```

- [ ] **Step 3: Verify visually**

Refresh `http://localhost:8800/` in browser.
Expected: two tabs appear, AI active, styled.

- [ ] **Step 4: Commit**

```bash
git add web/static/index.html web/static/style.css
git commit -m "feat(ui): add theme tab switcher markup and styling"
```

### Task 8.2: Wire theme tab to app.js + persist to localStorage

**Files:**
- Modify: `web/static/app.js`

- [ ] **Step 1: Identify where the existing fetch happens**

Read `web/static/app.js` to find the function that calls `/api/news` (likely `fetchNews()` or similar). This plan will assume it's called `fetchNews()` — adjust to the actual name.

- [ ] **Step 2: Add theme state + tab handlers**

At the top of `app.js` (or nearest to state management):

```javascript
const THEME_STORAGE_KEY = 'aggregator.activeTheme';

function getActiveTheme() {
  return localStorage.getItem(THEME_STORAGE_KEY) || 'ai';
}

function setActiveTheme(theme) {
  localStorage.setItem(THEME_STORAGE_KEY, theme);
  document.querySelectorAll('.theme-tab').forEach(btn => {
    const match = btn.dataset.theme === theme;
    btn.classList.toggle('active', match);
    btn.setAttribute('aria-selected', match ? 'true' : 'false');
  });
  // Re-fetch + re-render; adjust function name to match your codebase
  if (typeof fetchNews === 'function') fetchNews();
  if (typeof reloadFocusAreaFilters === 'function') reloadFocusAreaFilters();
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  const theme = getActiveTheme();
  setActiveTheme(theme);

  document.querySelectorAll('.theme-tab').forEach(btn => {
    btn.addEventListener('click', () => setActiveTheme(btn.dataset.theme));
  });
});
```

- [ ] **Step 3: Modify `fetchNews()` to include `theme` param**

Wherever the URL for `/api/news` is built, append `&theme=${encodeURIComponent(getActiveTheme())}`:

```javascript
// Example — adapt to existing code:
const params = new URLSearchParams({
  page: currentPage,
  page_size: pageSize,
  theme: getActiveTheme(),
  // ... existing params ...
});
const response = await fetch(`/api/news?${params}`);
```

- [ ] **Step 4: Smoke test**

Refresh the page, click 时尚 tab.
Expected: grid refreshes, likely shows 0 items (no fashion data collected yet, OR the new fashion RSS sources from Phase 4 if already collected). Network tab shows `/api/news?...&theme=fashion`.

Click AI tab, verify AI content returns.

- [ ] **Step 5: Commit**

```bash
git add web/static/app.js
git commit -m "feat(ui): wire theme tabs to /api/news fetch with localStorage persistence"
```

### Task 8.3: Scope focus_area filter to current theme

**Files:**
- Modify: `web/static/app.js` (and possibly `index.html` if the filter chips are server-rendered — they likely are not)

- [ ] **Step 1: Define per-theme focus_areas in frontend**

Since the config is server-side and the frontend already displays categories derived from data, the simplest approach is: **when theme changes, only show chips that are valid for that theme**.

If the existing frontend builds focus_area chips from `/api/stats` or hardcoded, modify it to ask for theme-specific stats:

In `app.js`, wherever focus_area filter chips are built, include theme in the stats query:

```javascript
async function reloadFocusAreaFilters() {
  const theme = getActiveTheme();
  const resp = await fetch(`/api/stats?theme=${encodeURIComponent(theme)}`);
  const stats = await resp.json();
  const byCategory = stats.by_category || {};
  // ... existing code that renders chips from byCategory ...
}
```

- [ ] **Step 2: Add theme parameter to `/api/stats`**

In `web/app.py`:

```python
@app.get("/api/stats")
def stats(
    date: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    theme: Optional[str] = Query(None),     # NEW
):
    db = _get_db()
    try:
        return db.get_stats(date=date, date_from=date_from, date_to=date_to, theme=theme)
    finally:
        db.close()
```

In `storage/database.py` `get_stats`:

```python
def get_stats(
    self,
    date: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    theme: str | None = None,              # NEW
) -> dict:
    conditions: list[str] = []
    params: list = []
    if date:
        conditions.append("collected_at LIKE ?")
        params.append(f"{date}%")
    elif date_from and date_to:
        conditions.append("collected_at >= ? AND collected_at <= ?")
        params.extend([f"{date_from}T00:00:00", f"{date_to}T23:59:59"])
    if theme:
        conditions.append("theme = ?")
        params.append(theme)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    # ... rest of existing code ...
```

- [ ] **Step 3: Smoke test**

Refresh, switch themes. Focus area chips should show only categories that exist for that theme (or be empty for fashion until content is collected).

- [ ] **Step 4: Commit**

```bash
git add web/static/app.js web/app.py storage/database.py
git commit -m "feat(ui): scope focus_area filter chips to active theme"
```

---

## Phase 9 — Frontend: Subscribe Modal

Modal triggered by `+ 添加订阅` button.

### Task 9.1: Subscribe modal HTML + CSS

**Files:**
- Modify: `web/static/index.html`
- Modify: `web/static/style.css`

- [ ] **Step 1: Add `<dialog>` element at the bottom of index.html body**

Before `</body>`:

```html
<dialog id="subscribe-modal" class="subscribe-modal">
  <form method="dialog" id="subscribe-form" onsubmit="return false;">
    <h2>添加订阅</h2>

    <div class="modal-state" data-state="input">
      <label for="subscribe-url">粘贴订阅链接（RSS / YouTube / Twitter / Bilibili / 小红书 / 微博）:</label>
      <input type="url" id="subscribe-url" placeholder="https://..." required>
      <button type="button" id="btn-analyze">分析</button>
    </div>

    <div class="modal-state" data-state="loading" hidden>
      <div class="spinner"></div>
      <p>正在分析中（抓取样本 + AI 判断），可能需要 5-15 秒...</p>
    </div>

    <div class="modal-state" data-state="result" hidden>
      <div id="result-already-subscribed" hidden>
        <p class="info">✓ 此源已在订阅中。</p>
      </div>
      <div id="result-previously-rejected" hidden>
        <p class="warning">⚠ 你之前拒绝过此源。</p>
        <button type="button" id="btn-reanalyze">重新分析</button>
      </div>

      <div id="result-main">
        <p><strong>已识别：</strong> <span id="r-type"></span></p>

        <h3>样本内容</h3>
        <ul id="r-sample"></ul>

        <h3>AI 建议</h3>
        <p><strong>理由：</strong> <span id="r-reasoning"></span></p>
        <p><strong>质量分：</strong> <span id="r-score"></span> / 10</p>

        <label>主题:
          <select id="r-theme">
            <option value="ai">🤖 AI</option>
            <option value="fashion">👗 时尚</option>
          </select>
        </label>

        <label>focus_area (多选):
          <select id="r-focus-areas" multiple size="4"></select>
        </label>

        <label>源名称:
          <input type="text" id="r-name">
        </label>

        <div class="modal-actions">
          <button type="button" id="btn-confirm-accept" class="btn-primary">确认订阅</button>
          <button type="button" id="btn-confirm-reject" class="btn-secondary">拒绝</button>
          <button type="button" id="btn-cancel" class="btn-tertiary">取消</button>
        </div>
      </div>
    </div>

    <div class="modal-state" data-state="error" hidden>
      <p class="error" id="error-message"></p>
      <button type="button" id="btn-retry">重试</button>
    </div>
  </form>
</dialog>
```

- [ ] **Step 2: Add CSS**

Append to `style.css`:

```css
dialog.subscribe-modal {
  max-width: 640px;
  width: 90%;
  padding: 24px;
  border: 1px solid var(--border, #333);
  border-radius: 8px;
  background: var(--bg, #1a1a1a);
  color: var(--text, #eee);
}

dialog.subscribe-modal::backdrop {
  background: rgba(0,0,0,0.6);
}

.modal-state { margin-top: 12px; }
.modal-state label { display: block; margin: 8px 0 4px; }
.modal-state input[type=url], .modal-state input[type=text], .modal-state select {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border, #444);
  border-radius: 4px;
  background: var(--bg-input, #222);
  color: var(--text, #eee);
}

.modal-actions {
  display: flex; gap: 8px; margin-top: 16px;
}

.btn-tertiary { background: transparent; color: var(--text-muted, #888); border: 1px solid var(--border, #444); }

.spinner {
  width: 24px; height: 24px;
  border: 3px solid var(--border, #444);
  border-top-color: var(--accent, #4a9eff);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin: 12px auto;
}

@keyframes spin { to { transform: rotate(360deg); } }

.error { color: #e74c3c; }
.warning { color: #e67e22; }
.info { color: #2ecc71; }

#r-sample { max-height: 200px; overflow-y: auto; padding-left: 18px; }
#r-sample li { margin-bottom: 6px; }
```

- [ ] **Step 3: Verify modal renders**

Refresh page. Click `+ 添加订阅` → nothing happens yet (JS in next task). But open DevTools → run `document.getElementById('subscribe-modal').showModal()`. The modal should appear centered with backdrop.

- [ ] **Step 4: Commit**

```bash
git add web/static/index.html web/static/style.css
git commit -m "feat(ui): subscribe modal markup and styling"
```

### Task 9.2: Subscribe modal JS logic

**Files:**
- Create: `web/static/subscribe-modal.js`
- Modify: `web/static/index.html`

- [ ] **Step 1: Create `web/static/subscribe-modal.js`**

```javascript
(function () {
  const FOCUS_AREAS_BY_THEME = {
    ai: ['开源模型', 'ComfyUI', '商用产品', 'Agent & Skills', '3D生成与重建', '训练与部署'],
    fashion: ['潮流', '时装', 'AI × 时尚'],
  };

  const modal = document.getElementById('subscribe-modal');
  const btnOpen = document.getElementById('btn-add-subscribe');
  const btnAnalyze = document.getElementById('btn-analyze');
  const btnAccept = document.getElementById('btn-confirm-accept');
  const btnReject = document.getElementById('btn-confirm-reject');
  const btnCancel = document.getElementById('btn-cancel');
  const btnRetry = document.getElementById('btn-retry');
  const btnReanalyze = document.getElementById('btn-reanalyze');

  let currentAnalysisId = null;

  function setState(name) {
    modal.querySelectorAll('.modal-state').forEach(el => {
      el.hidden = el.dataset.state !== name;
    });
  }

  function openModal() {
    document.getElementById('subscribe-url').value = '';
    setState('input');
    modal.showModal();
  }

  function closeModal() {
    modal.close();
    currentAnalysisId = null;
  }

  function renderFocusAreaOptions(theme, selected) {
    const select = document.getElementById('r-focus-areas');
    select.innerHTML = '';
    const all = FOCUS_AREAS_BY_THEME[theme] || [];
    for (const fa of all) {
      const opt = document.createElement('option');
      opt.value = fa;
      opt.textContent = fa;
      if (selected && selected.includes(fa)) opt.selected = true;
      select.appendChild(opt);
    }
  }

  async function doAnalyze(url) {
    setState('loading');
    try {
      const resp = await fetch('/api/subscribe/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      const result = await resp.json();
      showResult(result);
    } catch (e) {
      showError(e.message || 'Analysis failed');
    }
  }

  function showResult(result) {
    currentAnalysisId = result.analysis_id;
    setState('result');

    document.getElementById('result-already-subscribed').hidden = !result.already_subscribed;
    document.getElementById('result-previously-rejected').hidden = !result.previously_rejected;

    if (result.already_subscribed) {
      document.getElementById('result-main').hidden = true;
      return;
    }
    document.getElementById('result-main').hidden = false;

    document.getElementById('r-type').textContent = result.detected_type;
    document.getElementById('r-reasoning').textContent = result.llm.reasoning || '';
    document.getElementById('r-score').textContent = result.llm.quality_score ?? '-';

    const theme = result.llm.theme === 'fashion' ? 'fashion' : 'ai';
    document.getElementById('r-theme').value = theme;
    renderFocusAreaOptions(theme, result.llm.suggested_focus_areas || []);

    // Sample list
    const ul = document.getElementById('r-sample');
    ul.innerHTML = '';
    for (const s of (result.sample || [])) {
      const li = document.createElement('li');
      li.innerHTML = `<strong>${escapeHtml(s.title)}</strong><br>
                      <small>${escapeHtml((s.snippet || '').slice(0, 200))}</small>`;
      ul.appendChild(li);
    }

    // Pre-fill name
    const input = document.getElementById('r-name');
    if (!input.value) {
      try {
        const u = new URL(document.getElementById('subscribe-url').value);
        input.value = u.hostname.replace(/^www\./, '');
      } catch (_) { input.value = ''; }
    }

    // Emphasize button based on verdict
    const verdict = result.llm.verdict;
    btnAccept.classList.toggle('btn-primary', verdict !== 'reject');
    btnReject.classList.toggle('btn-primary', verdict === 'reject');
  }

  function showError(msg) {
    setState('error');
    document.getElementById('error-message').textContent = msg;
  }

  async function doConfirm(action) {
    if (!currentAnalysisId) return;
    const body = { analysis_id: currentAnalysisId, action };
    if (action === 'accept') {
      body.overrides = {
        theme: document.getElementById('r-theme').value,
        focus_areas: Array.from(document.getElementById('r-focus-areas').selectedOptions).map(o => o.value),
        name: document.getElementById('r-name').value.trim(),
      };
    }
    const resp = await fetch('/api/subscribe/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      showError('确认失败，请重试');
      return;
    }
    const data = await resp.json();
    alert(action === 'accept' ? '订阅已添加，下次采集生效。' : '已拒绝。');
    closeModal();
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  // Wire up once
  if (btnOpen) btnOpen.addEventListener('click', openModal);
  if (btnAnalyze) btnAnalyze.addEventListener('click', () => {
    const url = document.getElementById('subscribe-url').value.trim();
    if (!url) return;
    doAnalyze(url);
  });
  if (btnAccept) btnAccept.addEventListener('click', () => doConfirm('accept'));
  if (btnReject) btnReject.addEventListener('click', () => doConfirm('reject'));
  if (btnCancel) btnCancel.addEventListener('click', closeModal);
  if (btnRetry) btnRetry.addEventListener('click', () => setState('input'));
  if (btnReanalyze) btnReanalyze.addEventListener('click', () => {
    const url = document.getElementById('subscribe-url').value.trim();
    if (url) doAnalyze(url);
  });

  // Theme change updates focus_area options
  const themeSel = document.getElementById('r-theme');
  if (themeSel) {
    themeSel.addEventListener('change', () => {
      renderFocusAreaOptions(themeSel.value, []);
    });
  }
})();
```

- [ ] **Step 2: Add script tag to index.html**

Before `</body>`:

```html
<script src="/static/subscribe-modal.js"></script>
```

- [ ] **Step 3: Smoke test end-to-end**

1. Refresh the page.
2. Click `+ 添加订阅`. Modal opens.
3. Paste `https://hypebeast.com/feed` → click 分析. Expect loading → result showing sample items + LLM verdict.
4. Leave defaults, click `确认订阅`. Expect alert "订阅已添加...". Modal closes.
5. Verify with: `curl http://localhost:8800/api/subscribe/list`. Should see the subscription as `status=active`.

- [ ] **Step 4: Commit**

```bash
git add web/static/subscribe-modal.js web/static/index.html
git commit -m "feat(ui): subscribe modal interaction logic with LLM analyze + confirm flow"
```

---

## Phase 10 — Frontend: Subscription Management Page

### Task 10.1: subscribe.html table view

**Files:**
- Create: `web/static/subscribe.html`
- Create: `web/static/subscribe.js`
- Modify: `web/app.py`

- [ ] **Step 1: Create `web/static/subscribe.html`**

```html
<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8">
  <title>订阅管理</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <header>
    <h1>订阅管理</h1>
    <a href="/" class="btn-secondary">← 返回首页</a>
  </header>

  <main>
    <div class="status-tabs">
      <button class="status-tab active" data-status="">全部</button>
      <button class="status-tab" data-status="active">活跃</button>
      <button class="status-tab" data-status="pending">待处理</button>
      <button class="status-tab" data-status="rejected">已拒绝</button>
      <button class="status-tab" data-status="disabled">已禁用</button>
    </div>

    <table class="subscriptions-table">
      <thead>
        <tr>
          <th>名称</th>
          <th>类型</th>
          <th>主题</th>
          <th>focus_area</th>
          <th>状态</th>
          <th>最后抓取</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody id="subscriptions-body">
        <tr><td colspan="7">加载中...</td></tr>
      </tbody>
    </table>
  </main>

  <script src="/static/subscribe.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `web/static/subscribe.js`**

```javascript
(function () {
  let currentStatus = '';

  async function loadList() {
    const url = currentStatus
      ? `/api/subscribe/list?status=${encodeURIComponent(currentStatus)}`
      : '/api/subscribe/list';
    const resp = await fetch(url);
    if (!resp.ok) { alert('加载失败'); return; }
    const rows = await resp.json();
    render(rows);
  }

  function render(rows) {
    const tbody = document.getElementById('subscriptions-body');
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7">暂无数据</td></tr>';
      return;
    }

    tbody.innerHTML = rows.map(r => {
      const fa = (r.focus_areas || []).join(', ');
      const themeBadge = r.theme === 'fashion' ? '👗 时尚' : '🤖 AI';
      const fetchStatus = r.last_fetch_status === 'ok'
        ? '✓'
        : r.last_fetch_status
          ? `<span class="error" title="${escapeHtml(r.last_fetch_status)}">✗</span>`
          : '—';
      return `
        <tr>
          <td>${escapeHtml(r.name || r.url)}</td>
          <td>${escapeHtml(r.source_type)}</td>
          <td>${themeBadge}</td>
          <td>${escapeHtml(fa)}</td>
          <td>${escapeHtml(r.status)}</td>
          <td>${r.last_fetch_at || '—'} ${fetchStatus}</td>
          <td>
            ${r.status === 'active'
              ? `<button data-action="disable" data-id="${r.id}">禁用</button>`
              : r.status === 'disabled'
                ? `<button data-action="enable" data-id="${r.id}">启用</button>`
                : r.status === 'pending'
                  ? `<button data-action="accept" data-id="${r.id}">确认</button>`
                  : ''}
            <button data-action="delete" data-id="${r.id}">删除</button>
          </td>
        </tr>
      `;
    }).join('');

    tbody.querySelectorAll('button[data-action]').forEach(btn => {
      btn.addEventListener('click', onRowAction);
    });
  }

  async function onRowAction(evt) {
    const id = evt.target.dataset.id;
    const action = evt.target.dataset.action;
    let payload;
    let method = 'PATCH';

    if (action === 'disable') payload = { status: 'disabled' };
    else if (action === 'enable') payload = { status: 'active' };
    else if (action === 'accept') payload = { status: 'active' };
    else if (action === 'delete') {
      if (!confirm('删除这个订阅？')) return;
      method = 'DELETE';
      payload = null;
    }

    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (payload) opts.body = JSON.stringify(payload);

    const resp = await fetch(`/api/subscribe/${id}`, opts);
    if (!resp.ok) {
      alert('操作失败');
      return;
    }
    loadList();
  }

  document.querySelectorAll('.status-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.status-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentStatus = btn.dataset.status;
      loadList();
    });
  });

  function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
  }

  document.addEventListener('DOMContentLoaded', loadList);
})();
```

- [ ] **Step 3: Serve subscribe.html in web/app.py**

Add in `web/app.py`:

```python
@app.get("/subscribe.html")
def subscribe_page():
    return FileResponse(STATIC_DIR / "subscribe.html")
```

- [ ] **Step 4: Add status tabs + table styling**

Append to `style.css`:

```css
.status-tabs {
  display: flex; gap: 4px; margin-bottom: 16px;
}

.status-tab {
  padding: 6px 14px;
  border: 1px solid var(--border, #444);
  background: transparent;
  color: var(--text, #eee);
  cursor: pointer;
  border-radius: 4px;
}
.status-tab.active {
  background: var(--accent, #4a9eff);
  color: white;
  border-color: var(--accent, #4a9eff);
}

.subscriptions-table {
  width: 100%;
  border-collapse: collapse;
}
.subscriptions-table th, .subscriptions-table td {
  padding: 8px;
  border-bottom: 1px solid var(--border, #333);
  text-align: left;
  font-size: 0.9rem;
}
.subscriptions-table th { font-weight: 600; background: var(--bg-elevated, #222); }
```

- [ ] **Step 5: Smoke test**

Open `http://localhost:8800/subscribe.html`.
Expected: table renders. If the Hypebeast subscription from earlier exists, it shows. Click tabs to filter. Click "禁用" → row should re-render with updated status on next load.

- [ ] **Step 6: Commit**

```bash
git add web/static/subscribe.html web/static/subscribe.js web/static/style.css web/app.py
git commit -m "feat(ui): subscription management page with status filtering and row actions"
```

---

## Phase 11 — End-to-End Verification & Deployment Notes

### Task 11.1: End-to-end smoke test

**Files:** none

- [ ] **Step 1: Reset and full-pipeline test**

In a dev env with a clean DB:

Run: `rm -f data/news.db`
Run: `python main.py --skip-ai --no-proxy --days 2 -v 2>&1 | tail -50`

Expected:
- Auto-migration creates `news` table with `theme` column, plus `user_sources` table
- Fashion RSS feeds (Hypebeast, BoF, etc.) show up in collector logs
- Items saved with theme='fashion' for fashion feeds

Run:
```bash
sqlite3 data/news.db "SELECT theme, COUNT(*) FROM news GROUP BY theme"
```
Expected: rows showing `ai|<count>` and `fashion|<count>`.

- [ ] **Step 2: Full LLM pipeline test (if API key available)**

Run: `python main.py --days 1 -v 2>&1 | tail -80`

Expected: AI scorer processes items using per-theme prompts. Fashion items get fashion-flavored summaries.

- [ ] **Step 3: Web UI smoke**

Run: `python main.py --serve --port 8800`

Open `http://localhost:8800/`:
1. Toggle between AI and 时尚 tabs — items filter correctly
2. Click `+ 添加订阅` → paste a valid RSS URL → analyze → confirm → modal closes
3. Visit `/subscribe.html` → see the new subscription
4. Stop server, re-run `python main.py --no-proxy --skip-ai -v 2>&1 | grep "Merged"`
   Expected: log "Merged N dynamic user_sources into config"

- [ ] **Step 4: Commit**

No code change in this task. If anything failed, go back and fix the offending task.

### Task 11.2: Deployment notes

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add deployment section**

Append to `CLAUDE.md`:

```markdown
## v2 Migration Notes (Fashion Theme + Subscription Analyzer)

On next deploy:

1. Auto-migration runs on first startup (adds `theme` column to `news`, creates `user_sources` table). No manual step required.
2. If you prefer an explicit migration: `sqlite3 data/news.db < scripts/migrate_v2.sql`
3. Set `RSSHUB_URL` in `.env` (e.g., `RSSHUB_URL=http://localhost:1200`) for subscription analyzer to use RSSHub routes for 小红书/微博 URLs.
4. No rollback script needed — added column and table are backward-compatible.
5. Run tests after deploy: `pytest tests/ -v`
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: v2 migration notes for fashion theme + subscribe analyzer"
```

---

## Plan Self-Review Checklist

- [x] Spec section 3 (Data Model) → Tasks 1.1, 1.2, 5.1
- [x] Spec section 3.3 (Config) → Tasks 1.3, 3.2, 4.3, 6.5
- [x] Spec section 4 (Pipeline Integration) → Tasks 2.1, 2.2, 3.1, 4.1, 4.2, 5.3
- [x] Spec section 5 (Subscription Analyzer) → Tasks 6.1, 6.2, 6.3, 6.4, 6.5, 7.1
- [x] Spec section 6 (Frontend UI) → Tasks 8.1, 8.2, 8.3, 9.1, 9.2, 10.1
- [x] Spec section 7 (Migration) → Tasks 1.2, 5.1, 11.2
- [x] Spec section 8 (Error Handling) → Task 6.4 (LLM retry + fallback), 7.1 (cached states), 7.2 (status)
- [x] Spec section 9 (Testing) → Tasks 0.1, 0.2, 1.1-5.2 (TDD for high-risk)
- [x] Placeholder scan: no TBD/TODO/XXX/FIXME in plan body
- [x] Type consistency: `Theme` enum used consistently; `UserSource` dataclass used consistently; `DetectionResult` used consistently.

---

## Execution

Plan complete and saved to `docs/superpowers/plans/2026-04-21-fashion-theme-subscription.md`.
