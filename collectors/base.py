"""Core data models and base scraper interface."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import httpx
from pydantic import BaseModel, Field, HttpUrl


class SourceType(str, Enum):
    RSS = "rss"
    YOUTUBE = "youtube"
    BILIBILI = "bilibili"
    TWITTER = "twitter"
    GITHUB = "github"
    HACKERNEWS = "hackernews"
    REDDIT = "reddit"
    TELEGRAM = "telegram"
    HF_PAPERS = "hf_papers"
    MANUAL = "manual"


class Theme(str, Enum):
    AI = "ai"
    FASHION = "fashion"


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
    theme: Theme = Theme.AI
    image_url: Optional[str] = None

    # AI processing results (filled in Phase 3)
    ai_score: Optional[float] = None
    ai_summary: Optional[str] = None
    ai_categories: list[str] = Field(default_factory=list)
    ai_tags: list[str] = Field(default_factory=list)


class BaseScraper(ABC):
    """Abstract base class for all scrapers."""

    def __init__(self, config: dict, http_client: httpx.AsyncClient):
        self.config = config
        self.client = http_client

    @abstractmethod
    async def fetch(self, since: datetime) -> list[ContentItem]:
        """Fetch content items published since the given time."""

    def _generate_id(self, source: str, subtype: str, native_id: str) -> str:
        return f"{source}:{subtype}:{native_id}"
