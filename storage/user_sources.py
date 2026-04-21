"""CRUD for user_sources table."""

import hashlib
import logging
from dataclasses import dataclass
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
    """Update arbitrary fields on a user_source (theme, focus_areas, name, normalized_config)."""
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
