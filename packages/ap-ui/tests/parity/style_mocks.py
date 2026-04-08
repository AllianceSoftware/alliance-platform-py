from __future__ import annotations

from pathlib import Path
from typing import Any


class MockVanillaExtractMapping:
    def __init__(self, mapping: dict[str, Any]):
        self.mapping = mapping

    def __getattr__(self, name: str):
        return self.mapping.get(name, "")


DEFAULT_STYLE_MAPPINGS: dict[str, dict[str, Any]] = {
    "Button.css.ts": {
        "baseButton": "button-base",
        "sizes": {
            "sm": "button-size-sm",
            "md": "button-size-md",
            "lg": "button-size-lg",
            "xl": "button-size-xl",
            "2xl": "button-size-2xl",
        },
    },
    "focusRing.css.ts": {
        "base": "focus-ring-base",
    },
    "ButtonGroup.css.ts": {
        "buttonGroup": "button-group-base",
        "button": "button-group-button-slot",
    },
    "SmartOrientation.css.ts": {
        "container": {
            "horizontal": "so-horizontal",
            "vertical": "so-vertical",
        },
        "align": {
            "start": "so-align-start",
            "center": "so-align-center",
            "end": "so-align-end",
        },
        "density": {
            "compact": "so-density-compact",
            "xxs": "so-density-xxs",
            "xs": "so-density-xs",
            "sm": "so-density-sm",
            "md": "so-density-md",
            "lg": "so-density-lg",
            "xl": "so-density-xl",
            "xxl": "so-density-xxl",
            "xxxl": "so-density-xxxl",
        },
    },
}


def make_style_mapping_resolver(overrides: dict[str, dict[str, Any]] | None = None):
    mappings = {**DEFAULT_STYLE_MAPPINGS, **(overrides or {})}

    def _resolve_mapping(_bundler, filename):
        key = Path(filename).name
        return MockVanillaExtractMapping(mappings.get(key, {}))

    return _resolve_mapping
