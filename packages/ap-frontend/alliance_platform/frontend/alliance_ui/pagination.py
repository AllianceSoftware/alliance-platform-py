from pathlib import Path

from django import template
from django.template import Library

from ..bundler.base import ResolveContext
from ..templatetags.react import ComponentNode
from ..templatetags.react import ImportComponentSource
from ..templatetags.react import parse_component_tag
from .utils import get_module_import_source


class PaginationNode(ComponentNode):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        resolver_context = ResolveContext(self.bundler.root_dir, self.origin.name)
        self._render_pagination_item_link_path = self.bundler.resolve_path(
            "@alliancesoftware/ui",
            resolver_context,
            resolve_extensions=[".ts", ".tsx", ".js"],
        )
        # This make the component use links so changing page navigates to new URL
        self.props["renderItem"] = ImportComponentSource(
            self._render_pagination_item_link_path, "renderPaginationItemAsLink", False
        )

    def get_paths_for_bundling(self) -> list[Path]:
        paths = super().get_paths_for_bundling()
        # Need to include this in the bundled paths so available in final build
        paths.append(self._render_pagination_item_link_path)
        return paths


def pagination(parser: template.base.Parser, token: template.base.Token):
    """Render a ``Pagination`` component from the Alliance UI library with the specified props"""
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "Pagination", False, parser.origin),
        node_class=PaginationNode,
    )


def register_pagination(register: Library):
    register.tag("Pagination")(pagination)
