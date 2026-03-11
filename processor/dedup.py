"""Deduplication: URL exact match + title similarity + semantic dedup."""

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


def _normalize_tag(tag: str) -> str:
    """Normalize a tag for comparison."""
    return tag.lower().strip()


def _tags_overlap(tags_a: list[str], tags_b: list[str]) -> int:
    """Count matching tags between two items."""
    set_a = {_normalize_tag(t) for t in tags_a}
    set_b = {_normalize_tag(t) for t in tags_b}
    return len(set_a & set_b)


def deduplicate_semantic(
    items: list[ContentItem], min_shared_tags: int = 2
) -> list[ContentItem]:
    """Cross-source dedup using AI tag overlap.

    Two items are considered duplicates if they share >= min_shared_tags.
    Keeps the item with the highest AI score from each group.

    Args:
        items: Items with AI results populated (ai_tags required).
        min_shared_tags: Minimum shared tags to consider as duplicate.

    Returns:
        Deduplicated list, highest-scored item kept per group.
    """
    if not items:
        return items

    # Sort by score descending so highest-scored items are kept first
    scored = sorted(
        items,
        key=lambda x: (x.ai_score or -1),
        reverse=True,
    )

    kept: list[ContentItem] = []
    removed = 0

    for item in scored:
        if not item.ai_tags:
            kept.append(item)
            continue

        is_dup = False
        for kept_item in kept:
            if not kept_item.ai_tags:
                continue
            overlap = _tags_overlap(item.ai_tags, kept_item.ai_tags)
            if overlap >= min_shared_tags:
                is_dup = True
                removed += 1
                logger.debug(
                    "Semantic dedup: [%s] ≈ [%s] (shared %d tags)",
                    item.title[:40], kept_item.title[:40], overlap,
                )
                break

        if not is_dup:
            kept.append(item)

    if removed > 0:
        logger.info(
            "Semantic dedup: removed %d similar items, kept %d",
            removed, len(kept),
        )

    return kept
