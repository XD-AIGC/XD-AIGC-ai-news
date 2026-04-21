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
