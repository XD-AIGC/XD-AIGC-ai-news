"""Weekly digest: aggregate data, generate comics, output to GitHub Pages."""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collectors.base import ContentItem
from processor.comic_generator import ComicGenerator
from storage.database import NewsDatabase

logger = logging.getLogger(__name__)


def get_week_range(ref_date: datetime | None = None) -> tuple[str, str, str]:
    """Get the ISO week number and date range for the previous week.

    Returns: (week_label like '2026-W11', start_date, end_date) as YYYY-MM-DD.
    """
    if ref_date is None:
        ref_date = datetime.now(timezone.utc)

    # Go back to last Monday
    days_since_monday = ref_date.weekday()
    last_monday = ref_date - timedelta(days=days_since_monday + 7)
    last_sunday = last_monday + timedelta(days=6)

    iso_year, iso_week, _ = last_monday.isocalendar()
    week_label = f"{iso_year}-W{iso_week:02d}"
    start_date = last_monday.strftime("%Y-%m-%d")
    end_date = last_sunday.strftime("%Y-%m-%d")

    return week_label, start_date, end_date


async def generate_weekly_digest(
    db: NewsDatabase,
    comic_gen: ComicGenerator,
    output_dir: str = "./docs",
) -> dict | None:
    """Main weekly pipeline: query DB, generate comics, write output."""
    week_label, start_date, end_date = get_week_range()
    logger.info(
        "Weekly digest: %s (%s to %s)", week_label, start_date, end_date
    )

    # Get all items for the week
    all_items = db.get_items_by_date_range(start_date, end_date)
    if not all_items:
        logger.warning("No items found for %s, skipping weekly digest", week_label)
        return None

    # Get scored items sorted by score
    scored = [i for i in all_items if i.ai_score is not None]
    scored.sort(key=lambda x: x.ai_score or 0, reverse=True)
    top10 = scored[:10]

    if len(top10) < 3:
        logger.warning("Only %d scored items for %s, need at least 3", len(top10), week_label)
        return None

    # Count unique sources
    sources = {i.source_type.value for i in all_items}

    logger.info(
        "Weekly data: %d total items, %d scored, %d sources",
        len(all_items), len(scored), len(sources),
    )

    # Step 1: Generate script
    logger.info("Generating comic script...")
    script = await comic_gen.generate_script(top10, len(all_items), len(sources))
    logger.info("Script generated: %s", script.get("week_title", ""))

    # Step 2: Generate images
    week_dir = Path(output_dir) / "data" / "weekly" / week_label
    logger.info("Generating %d panel images...", sum(
        len(s.get("panels", [])) for s in script.get("stories", [])
    ))
    panel_paths = await comic_gen.generate_all_images(script, week_dir)

    # Step 3: Attach panel paths to script
    for si, story in enumerate(script.get("stories", [])):
        if si < len(panel_paths):
            story["panels_images"] = panel_paths[si]

    # Step 4: Build digest JSON
    # Category stats
    cat_counts: dict[str, int] = {}
    for item in all_items:
        for cat in item.ai_categories or []:
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

    digest = {
        "week": week_label,
        "date_range": f"{start_date} — {end_date}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_news": len(all_items),
        "total_sources": len(sources),
        "week_title": script.get("week_title", f"第{week_label}周报"),
        "editor_note": script.get("editor_note", ""),
        "stories": script.get("stories", []),
        "top10": [
            {"rank": i + 1, "title": item.title, "score": item.ai_score,
             "categories": item.ai_categories}
            for i, item in enumerate(top10)
        ],
        "stats": {
            "by_category": cat_counts,
            "by_source": {s: sum(1 for i in all_items if i.source_type.value == s) for s in sources},
        },
    }

    # Step 5: Write digest JSON
    digest_file = week_dir / "digest.json"
    digest_file.write_text(
        json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Step 6: Update weekly index
    _update_weekly_index(Path(output_dir) / "data" / "weekly", week_label, digest)

    logger.info("Weekly digest complete: %s (%d stories, %d panels)",
                week_label, len(digest["stories"]),
                sum(len(s.get("panels_images", [])) for s in digest["stories"]))

    return digest


def _update_weekly_index(weekly_dir: Path, week_label: str, digest: dict) -> None:
    """Update weekly/index.json with the new week entry."""
    index_file = weekly_dir / "index.json"
    weeks: list[dict] = []
    if index_file.exists():
        try:
            weeks = json.loads(index_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            weeks = []

    # Update or add
    existing = {w["week"]: w for w in weeks}
    existing[week_label] = {
        "week": week_label,
        "title": digest.get("week_title", ""),
        "date_range": digest.get("date_range", ""),
        "story_count": len(digest.get("stories", [])),
    }
    weeks = sorted(existing.values(), key=lambda w: w["week"], reverse=True)

    weekly_dir.mkdir(parents=True, exist_ok=True)
    index_file.write_text(
        json.dumps(weeks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
