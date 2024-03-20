from __future__ import annotations

from django import template
from django.template import Context
from django.template import Library

from common_frontend.bundler import get_bundler
from common_frontend.bundler.base import ResolveContext
from common_frontend.templatetags.react import ComponentNode
from common_frontend.templatetags.react import ImportComponentSource
from common_frontend.templatetags.react import NestedComponentPropAccumulator
from common_frontend.templatetags.react import parse_component_tag


def fragment_component(parser: template.base.Parser, token: template.base.Token):
    bundler = get_bundler()
    resolver_context = ResolveContext(bundler.root_dir, parser.origin.name if parser.origin else None)
    source_path = get_bundler().resolve_path(
        "re-exports", resolver_context, resolve_extensions=[".ts", ".tsx", ".js"]
    )
    asset_source = ImportComponentSource(source_path, "Fragment", False)
    return parse_component_tag(parser, token, asset_source=asset_source)


class RawHtmlNode(ComponentNode):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.props["html"] = self.props.pop("children")

    def render(self, context: Context):
        accumulator = NestedComponentPropAccumulator.get_current(context)
        if accumulator:
            return super().render(context)
        return self.render_html(context)

    def render_html(self, context):
        return self.resolve_prop(self.props["html"], context)


def raw_html(parser: template.base.Parser, token: template.base.Token):
    bundler = get_bundler()
    resolver_context = ResolveContext(bundler.root_dir, parser.origin.name if parser.origin else None)
    source_path = bundler.resolve_path(
        "components/RawHtmlWrapper", resolver_context, resolve_extensions=[".ts", ".tsx", ".js"]
    )
    asset_source = ImportComponentSource(source_path, "RawHtmlWrapper", True)
    return parse_component_tag(parser, token, asset_source=asset_source, node_class=RawHtmlNode)


def register_misc(register: Library):
    register.tag("Fragment")(fragment_component)
    register.tag("raw_html")(raw_html)
