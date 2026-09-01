from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
from typing import Literal

from alliance_platform.frontend.bundler import get_bundler
from alliance_platform.frontend.bundler.base import ResolveContext
from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from alliance_platform.frontend.bundler.frontend_resource import ImageResource
from django.template import Origin

IconStyle = Literal["outlined", "solid", "duotone", "duocolor"]

_ICON_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


@dataclass(frozen=True)
class StaticIconDefinition:
    name: str
    style: IconStyle
    svg_markup: str


def reset_static_icon_cache():
    """Clear the static icon cache. Intended for tests and development tooling."""
    _load_static_icon.cache_clear()


def validate_icon_name(name: str):
    if not isinstance(name, str) or not _ICON_NAME_RE.fullmatch(name):
        raise ValueError(f"Invalid icon name '{name}'")


def resolve_icon_style_dir(name: str) -> IconStyle:
    validate_icon_name(name)
    if name.endswith("Solid"):
        return "solid"
    if name.endswith("DuoTone"):
        return "duotone"
    if name.endswith("DuoColor"):
        return "duocolor"
    return "outlined"


def get_static_icon_request_path(name: str) -> str:
    style = resolve_icon_style_dir(name)
    return f"@alliancesoftware/icons/static-svg/{style}/{name}.svg"


def resolve_static_icon_path(name: str, *, origin: Origin | None = None) -> Path:
    bundler = get_bundler()
    resolver_context = ResolveContext(bundler.root_dir, origin.name if origin else None)
    return bundler.resolve_path(get_static_icon_request_path(name), resolver_context)


def get_static_icon_resource(name: str, *, origin: Origin | None = None) -> ImageResource:
    resource = FrontendResource.from_path(resolve_static_icon_path(name, origin=origin))
    if not isinstance(resource, ImageResource):
        raise TypeError(f"Expected static icon '{name}' to resolve to an image resource")
    return resource


def get_static_icon_definition(name: str, *, origin: Origin | None = None) -> StaticIconDefinition:
    style = resolve_icon_style_dir(name)
    source_path = resolve_static_icon_path(name, origin=origin)
    resource_path = get_bundler().get_resource_file_path(source_path)
    try:
        mtime_ns = resource_path.stat().st_mtime_ns
    except FileNotFoundError:
        mtime_ns = None
    return _load_static_icon(name, style, resource_path, mtime_ns)


@lru_cache(maxsize=512)
def _load_static_icon(
    name: str, style: IconStyle, resource_path: Path, mtime_ns: int | None
) -> StaticIconDefinition:
    """Load an icon, with path and mtime in the cache key for development invalidation."""
    svg_markup = resource_path.read_text()
    return StaticIconDefinition(name=name, style=style, svg_markup=svg_markup)
