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
