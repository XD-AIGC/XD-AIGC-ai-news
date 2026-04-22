"""Tests for load_themes shim and unified load_config."""

from pathlib import Path

import pytest

from storage.config_loader import load_config, load_themes


# ─── load_themes ─────────────────────────────────────


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


# ─── load_config ─────────────────────────────────────


def test_load_config_substitutes_env_vars(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MY_API_KEY", "sk-test-123")
    p = tmp_path / "c.yaml"
    p.write_text("llm:\n  api_key: ${MY_API_KEY}\n", encoding="utf-8")

    cfg = load_config(str(p))
    assert cfg["llm"]["api_key"] == "sk-test-123"


def test_load_config_keeps_literal_when_env_var_missing(tmp_path: Path, monkeypatch):
    """Missing env vars must NOT silently become empty strings — that's how prod sent
    `Bearer ` headers in the past. Keep the literal so callers can detect the problem."""
    monkeypatch.delenv("DEFINITELY_NOT_SET", raising=False)
    p = tmp_path / "c.yaml"
    p.write_text("llm:\n  api_key: ${DEFINITELY_NOT_SET}\n", encoding="utf-8")

    cfg = load_config(str(p))
    assert cfg["llm"]["api_key"] == "${DEFINITELY_NOT_SET}"


def test_load_config_handles_multiple_env_vars(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("A", "alpha")
    monkeypatch.setenv("B", "beta")
    p = tmp_path / "c.yaml"
    p.write_text(
        "outer:\n  one: ${A}\n  two: ${B}\n  combined: ${A}-${B}\n",
        encoding="utf-8",
    )

    cfg = load_config(str(p))
    assert cfg["outer"] == {"one": "alpha", "two": "beta", "combined": "alpha-beta"}


def test_load_config_default_path(monkeypatch, tmp_path: Path):
    """Default path is 'config.yaml' relative to cwd."""
    p = tmp_path / "config.yaml"
    p.write_text("foo: bar\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    cfg = load_config()
    assert cfg == {"foo": "bar"}


def test_load_config_raises_on_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(str(tmp_path / "does-not-exist.yaml"))
