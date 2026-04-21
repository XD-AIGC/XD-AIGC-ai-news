"""Tests for load_themes shim."""

from storage.config_loader import load_themes


def test_load_new_themes_format():
    config = {
        "themes": {
            "ai": [{"name": "开源模型", "keywords": ["stable diffusion"]}],
            "fashion": [{"name": "潮流", "keywords": ["streetwear"]}],
        }
    }
    themes = load_themes(config)
    assert "ai" in themes
    assert "fashion" in themes
    assert themes["ai"][0]["name"] == "开源模型"


def test_load_legacy_focus_areas_wraps_into_ai():
    config = {
        "focus_areas": [{"name": "ComfyUI", "keywords": ["comfyui"]}]
    }
    themes = load_themes(config)
    assert "ai" in themes
    assert len(themes["ai"]) == 1
    assert themes["ai"][0]["name"] == "ComfyUI"
    assert "fashion" not in themes


def test_load_empty_config_returns_empty_ai():
    themes = load_themes({})
    assert themes == {"ai": []}


def test_themes_takes_precedence_over_focus_areas():
    # If both are present (shouldn't happen but be defensive), themes wins
    config = {
        "themes": {"ai": [{"name": "A", "keywords": []}]},
        "focus_areas": [{"name": "B", "keywords": []}],
    }
    themes = load_themes(config)
    assert themes["ai"][0]["name"] == "A"
