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
}


def make_style_mapping_resolver(overrides: dict[str, dict[str, Any]] | None = None):
    mappings = {**DEFAULT_STYLE_MAPPINGS, **(overrides or {})}

    def _resolve_mapping(_bundler, filename):
        key = Path(filename).name
        scope = _mapping_scope_from_filename(key)
        return MockVanillaExtractMapping(scope, mappings.get(key, {}))

    return _resolve_mapping
