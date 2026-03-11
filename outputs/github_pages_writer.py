"""Export news data as static JSON files for GitHub Pages."""

import json
import logging
from pathlib import Path

from collectors.base import ContentItem

logger = logging.getLogger(__name__)


class GitHubPagesWriter:
    """Export items to static JSON files in docs/ for GitHub Pages hosting."""

    def __init__(self, output_dir: str = "./docs"):
        self.output_dir = Path(output_dir)
        self.data_dir = self.output_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def write(self, items: list[ContentItem], date: str) -> Path:
        """Write items as JSON for a given date and update the index."""
        # Write date-specific JSON
        date_file = self.data_dir / f"{date}.json"
        news_data = [self._item_to_dict(item) for item in items]
        # Sort by ai_score descending, then by collected_at descending
        news_data.sort(
            key=lambda x: (x["ai_score"] or -1, x["collected_at"]),
            reverse=True,
        )
        date_file.write_text(
            json.dumps(news_data, ensure_ascii=False, indent=None),
            encoding="utf-8",
        )

        # Update dates index
        self._update_dates_index(date, len(items))

        # Compute stats for this date
        self._write_stats(date, items)

        logger.info(
            "GitHub Pages: wrote %d items to %s", len(items), date_file
        )
        return date_file

    def _update_dates_index(self, date: str, count: int) -> None:
        """Update docs/data/dates.json with available dates."""
        index_file = self.data_dir / "dates.json"
        dates: list[dict] = []
        if index_file.exists():
            try:
                dates = json.loads(index_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                dates = []

        # Update or add
        existing = {d["date"]: d for d in dates}
        existing[date] = {"date": date, "count": count}
        dates = sorted(existing.values(), key=lambda d: d["date"], reverse=True)

        index_file.write_text(
            json.dumps(dates, ensure_ascii=False), encoding="utf-8"
        )

    def _write_stats(self, date: str, items: list[ContentItem]) -> None:
        """Write stats JSON for a specific date."""
        by_source: dict[str, int] = {}
        by_category: dict[str, int] = {}

        for item in items:
            src = item.source_type.value
            by_source[src] = by_source.get(src, 0) + 1
            for cat in item.ai_categories:
                by_category[cat] = by_category.get(cat, 0) + 1

        stats = {
            "total": len(items),
            "by_source": by_source,
            "by_category": by_category,
        }

        stats_file = self.data_dir / f"stats-{date}.json"
        stats_file.write_text(
            json.dumps(stats, ensure_ascii=False), encoding="utf-8"
        )

    @staticmethod
    def _item_to_dict(item: ContentItem) -> dict:
        return {
            "id": item.id,
            "source_type": item.source_type.value,
            "title": item.title,
            "url": item.url,
            "content": item.content[:500] if item.content else "",
            "author": item.author,
            "published_at": item.published_at.isoformat()
            if item.published_at else None,
            "collected_at": item.collected_at.isoformat(),
            "ai_score": item.ai_score,
            "ai_summary": item.ai_summary,
            "ai_categories": item.ai_categories,
            "ai_tags": item.ai_tags,
        }
