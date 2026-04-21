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
