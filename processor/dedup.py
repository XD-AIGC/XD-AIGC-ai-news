"""Deduplication: URL exact match + title similarity."""

import logging
import re

from collectors.base import ContentItem

logger = logging.getLogger(__name__)


def normalize_title(title: str) -> str:
    """Normalize title for comparison."""
    title = title.lower().strip()
    title = re.sub(r"[\[\(（【].*?[\]\)）】]", "", title)
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip()


def jaccard_similarity(a: str, b: str) -> float:
    """Word-level Jaccard similarity between two strings."""
    words_a = set(normalize_title(a).split())
    words_b = set(normalize_title(b).split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def deduplicate(
    items: list[ContentItem], threshold: float = 0.7
) -> list[ContentItem]:
    """Remove duplicates by URL and title similarity.

    Args:
        items: List of content items to deduplicate.
        threshold: Jaccard similarity threshold (0.0-1.0).

    Returns:
        Deduplicated list of items.
    """
    seen_urls: set[str] = set()
    kept_titles: list[str] = []
    result: list[ContentItem] = []
    removed = 0

    for item in items:
        url_key = item.url.rstrip("/").lower()
        if url_key in seen_urls:
            removed += 1
            continue
        seen_urls.add(url_key)

        is_dup = False
        for kept in kept_titles:
            if jaccard_similarity(item.title, kept) >= threshold:
                is_dup = True
                removed += 1
                break

        if not is_dup:
            kept_titles.append(item.title)
            result.append(item)

    if removed > 0:
        logger.info("Dedup: removed %d duplicates, kept %d", removed, len(result))

    return result
