"""SQLite schema definitions."""

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
    image_url TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
"""

CREATE_INDEX_URL = """
CREATE INDEX IF NOT EXISTS idx_news_url ON news(url);
"""

CREATE_INDEX_DATE = """
CREATE INDEX IF NOT EXISTS idx_news_collected ON news(collected_at);
"""

CREATE_INDEX_SOURCE = """
CREATE INDEX IF NOT EXISTS idx_news_source ON news(source_type);
"""

CREATE_INDEX_SCORE = """
CREATE INDEX IF NOT EXISTS idx_news_score ON news(ai_score);
"""

CREATE_INDEX_THEME = """
CREATE INDEX IF NOT EXISTS idx_news_theme ON news(theme);
"""

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
