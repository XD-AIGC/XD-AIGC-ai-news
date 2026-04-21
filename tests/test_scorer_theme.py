"""Tests for per-theme prompt selection in AIScorer."""

from collectors.base import ContentItem, SourceType, Theme
from processor.scorer import AIScorer


def test_scorer_picks_theme_prompt():
    config = {
        "model": "fake-model",
        "api_key": "fake",
        "scoring_prompts": {
            "ai": "AI ANALYST PROMPT",
            "fashion": "FASHION ANALYST PROMPT",
        },
    }
    scorer = AIScorer(config)

    ai_item = ContentItem(
        id="1", source_type=SourceType.RSS, title="T", url="u",
        theme=Theme.AI,
    )
    fashion_item = ContentItem(
        id="2", source_type=SourceType.RSS, title="T", url="u",
        theme=Theme.FASHION,
    )

    assert "AI ANALYST" in scorer._system_prompt_for(ai_item)
    assert "FASHION ANALYST" in scorer._system_prompt_for(fashion_item)


def test_scorer_falls_back_to_legacy_prompt_when_no_scoring_prompts():
    # Back-compat: if config has no scoring_prompts, use the module-level SYSTEM_PROMPT
    from processor.scorer import SYSTEM_PROMPT

    config = {"model": "m", "api_key": "k"}  # no scoring_prompts
    scorer = AIScorer(config)

    item = ContentItem(
        id="1", source_type=SourceType.RSS, title="T", url="u",
        theme=Theme.AI,
    )
    assert scorer._system_prompt_for(item) == SYSTEM_PROMPT


def test_scorer_missing_theme_prompt_falls_back_to_ai_prompt():
    config = {
        "model": "m", "api_key": "k",
        "scoring_prompts": {"ai": "AI PROMPT"},  # fashion missing
    }
    scorer = AIScorer(config)

    fashion_item = ContentItem(
        id="1", source_type=SourceType.RSS, title="T", url="u",
        theme=Theme.FASHION,
    )
    # Missing → fall back to ai
    assert scorer._system_prompt_for(fashion_item) == "AI PROMPT"


def test_allowed_categories_ai_includes_ai_focus_areas():
    ai_item = ContentItem(
        id="1", source_type=SourceType.RSS, title="T", url="u", theme=Theme.AI,
    )
    cats = AIScorer._allowed_categories_for(ai_item)
    # AI picklist must include existing AI focus_areas and NOT fashion ones
    assert '"开源模型"' in cats
    assert '"ComfyUI"' in cats
    assert '"其他"' in cats
    assert '"潮流"' not in cats
    assert '"时装"' not in cats


def test_allowed_categories_fashion_includes_fashion_focus_areas():
    fashion_item = ContentItem(
        id="1", source_type=SourceType.RSS, title="T", url="u", theme=Theme.FASHION,
    )
    cats = AIScorer._allowed_categories_for(fashion_item)
    # Fashion picklist must include fashion focus_areas and NOT AI ones
    assert '"潮流"' in cats
    assert '"时装"' in cats
    assert '"AI × 时尚"' in cats
    assert '"其他"' in cats
    assert '"开源模型"' not in cats
    assert '"ComfyUI"' not in cats


def test_allowed_categories_unknown_theme_falls_back_to_ai():
    # Defensive: if somehow theme is a string that isn't ai/fashion, use ai picklist
    item = ContentItem(
        id="1", source_type=SourceType.RSS, title="T", url="u",
    )
    item.theme = "unknown_theme"  # simulate legacy/weird data
    cats = AIScorer._allowed_categories_for(item)
    assert '"开源模型"' in cats
