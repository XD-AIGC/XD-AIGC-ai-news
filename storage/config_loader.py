"""Config loader shim supporting both legacy focus_areas and new themes formats."""

import logging
import os
import re

import yaml

logger = logging.getLogger(__name__)


_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def load_config(config_path: str = "config.yaml") -> dict:
    """Read a YAML file and resolve ${ENV_VAR} substitutions.

    Missing env vars keep their `${VAR}` literal so downstream code can
    detect the misconfiguration loudly. Substituting silently with `""`
    once produced `Authorization: Bearer ` headers in production.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        raw = f.read()

    def replace(match: re.Match) -> str:
        var_name = match.group(1)
        return os.getenv(var_name, match.group(0))

    resolved = _ENV_VAR_PATTERN.sub(replace, raw)
    return yaml.safe_load(resolved)


def load_themes(config: dict) -> dict[str, list[dict]]:
    """Return themes mapping from config, accepting legacy or new format.

    New format (preferred):
        themes:
          ai: [ {name, keywords}, ... ]
          fashion: [ ... ]

    Legacy format:
        focus_areas: [ {name, keywords}, ... ]
        -> wrapped as {"ai": [...]}
    """
    if "themes" in config and isinstance(config["themes"], dict):
        return config["themes"]

    if "focus_areas" in config:
        logger.info(
            "Legacy 'focus_areas' config detected, wrapping as themes.ai. "
            "Consider migrating to the 'themes' format."
        )
        return {"ai": config["focus_areas"]}

    return {"ai": []}
