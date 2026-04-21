"""Shared pytest fixtures."""

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
