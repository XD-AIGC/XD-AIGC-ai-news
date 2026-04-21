"""Config loader shim supporting both legacy focus_areas and new themes formats."""

import logging

logger = logging.getLogger(__name__)


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
