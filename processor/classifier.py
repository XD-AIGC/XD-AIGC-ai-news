"""Keyword-based fallback classifier (no LLM required)."""

import logging

from collectors.base import ContentItem

logger = logging.getLogger(__name__)


class KeywordClassifier:
    """Classify items into focus areas based on keyword matching.

    Used as a fallback when AI scoring is not available,
    or as a pre-filter before AI processing.
    """

    def __init__(self, focus_areas: list[dict]):
        self.areas: list[tuple[str, set[str]]] = []
        for area in focus_areas:
            name = area["name"]
            keywords = {kw.lower() for kw in area.get("keywords", [])}
            self.areas.append((name, keywords))

    def classify(self, item: ContentItem) -> list[str]:
        """Return matching focus area names for an item."""
        text = f"{item.title} {item.content[:500]}".lower()
        matches = []
        for name, keywords in self.areas:
            if any(kw in text for kw in keywords):
                matches.append(name)
        return matches if matches else ["其他"]

    def classify_items(
        self, items: list[ContentItem], overwrite: bool = False
    ) -> list[ContentItem]:
        """Classify items that don't already have categories."""
        classified = 0
        for item in items:
            if item.ai_categories and not overwrite:
                continue
            item.ai_categories = self.classify(item)
            classified += 1

        logger.info("Keyword classifier: classified %d items", classified)
        return items

    def filter_relevant(self, items: list[ContentItem]) -> list[ContentItem]:
        """Keep only items that match at least one focus area (not '其他')."""
        relevant = []
        for item in items:
            cats = self.classify(item)
            if cats != ["其他"]:
                relevant.append(item)

        logger.info(
            "Relevance filter: %d -> %d items", len(items), len(relevant)
        )
        return relevant
