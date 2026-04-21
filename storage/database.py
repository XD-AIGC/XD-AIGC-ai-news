"""SQLite database operations."""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from collectors.base import ContentItem
from storage.models import (
    CREATE_INDEX_DATE,
    CREATE_INDEX_SCORE,
    CREATE_INDEX_SOURCE,
    CREATE_INDEX_THEME,
    CREATE_INDEX_URL,
    CREATE_INDEX_USER_SOURCES_STATUS,
    CREATE_NEWS_TABLE,
    CREATE_USER_SOURCES_TABLE,
)

logger = logging.getLogger(__name__)


class NewsDatabase:
    def __init__(self, db_path: str = "./data/news.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

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
        cursor.execute(CREATE_USER_SOURCES_TABLE)
        cursor.execute(CREATE_INDEX_USER_SOURCES_STATUS)
        self._conn.commit()

    def url_exists(self, url: str) -> bool:
        cursor = self._conn.cursor()
        cursor.execute("SELECT 1 FROM news WHERE url = ?", (url,))
        return cursor.fetchone() is not None

    def save_items(self, items: list[ContentItem]) -> int:
        """Save items to database, skip duplicates. Returns count of new items."""
        new_count = 0
        cursor = self._conn.cursor()

        for item in items:
            if self.url_exists(item.url):
                continue
            try:
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
                new_count += 1
            except sqlite3.IntegrityError:
                logger.debug("Duplicate item skipped: %s", item.url)

        self._conn.commit()
        return new_count

    def get_items_by_date(
        self, date: str, source_type: str | None = None
    ) -> list[ContentItem]:
        """Get items collected on a specific date (YYYY-MM-DD)."""
        query = "SELECT * FROM news WHERE collected_at LIKE ?"
        params: list = [f"{date}%"]

        if source_type:
            query += " AND source_type = ?"
            params.append(source_type)

        query += " ORDER BY ai_score DESC NULLS LAST, published_at DESC"

        cursor = self._conn.cursor()
        cursor.execute(query, params)
        return [self._row_to_item(row) for row in cursor.fetchall()]

    def get_items_by_date_range(
        self, start_date: str, end_date: str, min_score: float | None = None
    ) -> list[ContentItem]:
        """Get items collected between start_date and end_date (inclusive, YYYY-MM-DD)."""
        query = "SELECT * FROM news WHERE collected_at >= ? AND collected_at <= ?"
        params: list = [f"{start_date}T00:00:00", f"{end_date}T23:59:59"]

        if min_score is not None:
            query += " AND ai_score >= ?"
            params.append(min_score)

        query += " ORDER BY ai_score DESC NULLS LAST, collected_at DESC"

        cursor = self._conn.cursor()
        cursor.execute(query, params)
        return [self._row_to_item(row) for row in cursor.fetchall()]

    def update_ai_results(self, items: list[ContentItem]) -> int:
        """Update AI analysis results for existing items."""
        updated = 0
        cursor = self._conn.cursor()
        for item in items:
            cursor.execute(
                """UPDATE news SET
                    ai_score = ?, ai_summary = ?,
                    ai_categories = ?, ai_tags = ?
                WHERE id = ?""",
                (
                    item.ai_score,
                    item.ai_summary,
                    json.dumps(item.ai_categories, ensure_ascii=False),
                    json.dumps(item.ai_tags, ensure_ascii=False),
                    item.id,
                ),
            )
            if cursor.rowcount > 0:
                updated += 1
        self._conn.commit()
        logger.info("Updated AI results for %d items", updated)
        return updated

    def get_recent_items(
        self, limit: int = 100, min_score: float | None = None
    ) -> list[ContentItem]:
        """Get recent items, optionally filtered by minimum AI score."""
        query = "SELECT * FROM news"
        params: list = []

        if min_score is not None:
            query += " WHERE ai_score >= ?"
            params.append(min_score)

        query += " ORDER BY collected_at DESC LIMIT ?"
        params.append(limit)

        cursor = self._conn.cursor()
        cursor.execute(query, params)
        return [self._row_to_item(row) for row in cursor.fetchall()]

    def get_available_dates(self) -> list[dict]:
        """Return dates that have data, with item counts, newest first."""
        cursor = self._conn.cursor()
        cursor.execute(
            """SELECT substr(collected_at, 1, 10) AS date, COUNT(*) AS count
            FROM news GROUP BY date ORDER BY date DESC"""
        )
        return [{"date": row["date"], "count": row["count"]} for row in cursor.fetchall()]

    def get_stats(
        self,
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        theme: str | None = None,
    ) -> dict:
        """Return aggregate stats: source/category breakdowns."""
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

        cursor = self._conn.cursor()

        cursor.execute(f"SELECT COUNT(*) AS total FROM news {where}", params)
        total = cursor.fetchone()["total"]

        cursor.execute(
            f"SELECT source_type, COUNT(*) AS count FROM news {where} GROUP BY source_type",
            params,
        )
        by_source = {row["source_type"]: row["count"] for row in cursor.fetchall()}

        cursor.execute(
            f"SELECT ai_categories FROM news {where} AND ai_categories != '[]'"
            if where else
            "SELECT ai_categories FROM news WHERE ai_categories != '[]'",
            params,
        )
        cat_counts: dict[str, int] = {}
        for row in cursor.fetchall():
            for cat in json.loads(row["ai_categories"] or "[]"):
                cat_counts[cat] = cat_counts.get(cat, 0) + 1

        return {"total": total, "by_source": by_source, "by_category": cat_counts}

    def search_items(
        self,
        date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        source: str | None = None,
        category: str | None = None,
        theme: str | None = None,
        q: str | None = None,
        min_score: float | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ContentItem], int]:
        """Multi-filter paginated search. Returns (items, total_count)."""
        conditions: list[str] = []
        params: list = []

        if date:
            conditions.append("collected_at LIKE ?")
            params.append(f"{date}%")
        elif date_from and date_to:
            conditions.append("collected_at >= ? AND collected_at <= ?")
            params.extend([f"{date_from}T00:00:00", f"{date_to}T23:59:59"])
        elif date_from:
            conditions.append("collected_at >= ?")
            params.append(f"{date_from}T00:00:00")
        elif date_to:
            conditions.append("collected_at <= ?")
            params.append(f"{date_to}T23:59:59")
        if source:
            conditions.append("source_type = ?")
            params.append(source)
        if category:
            conditions.append("ai_categories LIKE ?")
            params.append(f"%{category}%")
        if theme:
            conditions.append("theme = ?")
            params.append(theme)
        if q:
            conditions.append("(title LIKE ? OR content LIKE ? OR ai_summary LIKE ?)")
            pattern = f"%{q}%"
            params.extend([pattern, pattern, pattern])
        if min_score is not None:
            conditions.append("ai_score >= ?")
            params.append(min_score)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        cursor = self._conn.cursor()
        cursor.execute(f"SELECT COUNT(*) AS cnt FROM news {where}", params)
        total = cursor.fetchone()["cnt"]

        offset = (page - 1) * page_size
        query = (
            f"SELECT * FROM news {where} "
            "ORDER BY ai_score DESC NULLS LAST, collected_at DESC "
            "LIMIT ? OFFSET ?"
        )
        params.extend([page_size, offset])

        cursor.execute(query, params)
        items = [self._row_to_item(row) for row in cursor.fetchall()]
        return items, total

    def _row_to_item(self, row: sqlite3.Row) -> ContentItem:
        from collectors.base import Theme
        # Row may lack theme column in pre-migration dev DBs; default to ai
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
