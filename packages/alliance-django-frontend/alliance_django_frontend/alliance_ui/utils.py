from __future__ import annotations

from django.template import Origin
from django.template.base import UNKNOWN_SOURCE

from ..bundler import get_bundler
from ..bundler.base import ResolveContext
from ..templatetags.react import ImportComponentSource


def get_module_import_source(
    path: str, name: str, is_default_export: bool, origin: Origin | None, property_name: str | None = None
):
    """Create an ImportComponentSource for a node_modules module

    Args:
        name: The name of the export. This should be a named export from the alliance-ui package
        origin: The template origin
        property_name: Optional property name. Useful for exports like `Menubar` that have attached properties
            like `Menubar.Item`.

    Returns:
        The ``ImportComponentSource`` that can then be passed to ``parse_component_tag``
    """
    if origin is None:
        origin = Origin(UNKNOWN_SOURCE)
    bundler = get_bundler()
    resolver_context = ResolveContext(bundler.root_dir, origin.name)
    source_path = get_bundler().resolve_path(
        path, resolver_context, resolve_extensions=[".ts", ".tsx", ".js"]
    )
    return ImportComponentSource(source_path, name, is_default_export, property_name=property_name)
