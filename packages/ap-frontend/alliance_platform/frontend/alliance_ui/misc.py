from __future__ import annotations

from django import template
from django.template import Library

from ..bundler import get_bundler
from ..bundler.base import ResolveContext
from ..templatetags.react import ImportComponentSource
from ..templatetags.react import parse_component_tag


def fragment_component(parser: template.base.Parser, token: template.base.Token):
    """Render a React Fragment component."""
    bundler = get_bundler()
    resolver_context = ResolveContext(bundler.root_dir, parser.origin.name if parser.origin else None)
    source_path = get_bundler().resolve_path(
        "/node_modules/react", resolver_context, resolve_extensions=[".ts", ".tsx", ".js"]
    )
    asset_source = ImportComponentSource(source_path, "React", True, "Fragment")
    return parse_component_tag(parser, token, asset_source=asset_source)


def register_misc(register: Library):
    register.tag("Fragment")(fragment_component)
