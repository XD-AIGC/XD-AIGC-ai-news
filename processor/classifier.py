"""Theme-scoped keyword classifier (no LLM required)."""

import logging

from collectors.base import ContentItem, Theme

logger = logging.getLogger(__name__)


class KeywordClassifier:
    """Classify items into focus areas, scoped to the item's theme.

    An AI item only matches keywords from themes['ai']; a fashion item only
    matches keywords from themes['fashion']. This prevents cross-theme mis-tagging.
    """

    def __init__(self, themes: dict[str, list[dict]]):
        # themes is {"ai": [{name, keywords}, ...], "fashion": [...]}
        self.themes: dict[str, list[tuple[str, set[str]]]] = {}
        for theme_name, areas in themes.items():
            compiled: list[tuple[str, set[str]]] = []
            for area in areas:
                name = area["name"]
                keywords = {kw.lower() for kw in area.get("keywords", [])}
                compiled.append((name, keywords))
            self.themes[theme_name] = compiled

    def classify(self, item: ContentItem) -> list[str]:
        """Return matching focus area names, scoped to item's theme."""
        theme_key = item.theme.value if isinstance(item.theme, Theme) else item.theme
        areas = self.themes.get(theme_key, [])
        if not areas:
            return ["其他"]

        text = f"{item.title} {item.content[:500]}".lower()
        matches = []
        for name, keywords in areas:
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
        """Keep only items matching at least one focus area (not '其他')."""
        relevant = []
        for item in items:
            cats = self.classify(item)
            if cats != ["其他"]:
                relevant.append(item)

        logger.info("Relevance filter: %d -> %d items", len(items), len(relevant))
        return relevant
