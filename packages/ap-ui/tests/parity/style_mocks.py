from __future__ import annotations

from pathlib import Path
from typing import Any


class MockStyleToken(str):
    """String token that can also synthesise nested class keys via `.get(...)`."""

    def __new__(cls, token: str):
        return super().__new__(cls, token)

    def get(self, key: str, default: str = "") -> str:
        if not key:
            return default
        return f"{self}_{key}"


class MockVanillaExtractMapping:
    def __init__(self, scope: str, mapping: dict[str, Any]):
        self.scope = scope
        self.mapping = mapping

    def __getattr__(self, name: str):
        if name in self.mapping:
            value = self.mapping[name]
            if isinstance(value, dict):
                return value
            if isinstance(value, str):
                return value
        return MockStyleToken(f"{self.scope}_{name}")


def _mapping_scope_from_filename(filename: str) -> str:
    if filename.endswith(".css.ts"):
        return filename[: -len(".css.ts")]
    return Path(filename).stem


DEFAULT_STYLE_MAPPINGS: dict[str, dict[str, Any]] = {
    "SmartOrientation.css.ts": {
        "container": {
            "horizontal": "SmartOrientation_containerBase",
            "vertical": "SmartOrientation_containerBase",
        },
    },
    "Table.css.ts": {
        # The theme contract vars are serialized as var() references; only columnWidth is used
        # by the static renderer (for the column width prop).
        "vars": {
            "columnWidth": "var(--components-table-columnWidth)",
        },
        # sortIconUnsorted is composed from sortIcon (style([sortIcon, ...])) so the serialized
        # mapping value contains both classes.
        "sortIconUnsorted": "Table_sortIconUnsorted Table_sortIcon",
    },
    "Menubar.css.ts": {
        # menubarMenuItem is composed from menubarMenuItemBase (style([font, base])) so the
        # serialized mapping value contains both classes (font classes are outside the Menubar
        # scope and stripped from parity fixtures).
        "menubarMenuItem": "Menubar_menubarMenuItem Menubar_menubarMenuItemBase",
        # The level theme var is serialized as a var() reference; the static renderer sets it as
        # an inline style on submenu popup menus (matching assignInlineVars in React).
        "vars": {
            "level": "var(--level)",
        },
    },
    "LabeledInput.css.ts": {
        # Mirrors the recipe structure serialized by @alliancesoftware/vite-plugin-django-vanilla-extract
        "labeledInput": {
            "base": "LabeledInput_labeledInput",
            "variants": {
                "inputSize": {
                    "sm": "LabeledInput_labeledInput_inputSize_sm",
                    "md": "LabeledInput_labeledInput_inputSize_md",
                },
                "labelPosition": {
                    "top": "LabeledInput_labeledInput_labelPosition_top",
                    "side": "LabeledInput_labeledInput_labelPosition_side",
                },
            },
        },
    },
}


def make_style_mapping_resolver(overrides: dict[str, dict[str, Any]] | None = None):
    mappings = {**DEFAULT_STYLE_MAPPINGS, **(overrides or {})}

    def _resolve_mapping(_bundler, filename):
        key = Path(filename).name
        scope = _mapping_scope_from_filename(key)
        return MockVanillaExtractMapping(scope, mappings.get(key, {}))

    return _resolve_mapping
