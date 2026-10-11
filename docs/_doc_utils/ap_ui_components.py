"""Sphinx extension: the ``ui-component`` directive documents a static ``{% ui %}`` component.

``.. ui-component:: button`` writes the reference for the component registered as ``button``,
read from its renderer: the tag, its ``data-apui`` marker, slot, required parent, runtime token
and React tag, a table of its props, and the attributes it forwards and the props it refuses (see
``ap_ui_component_reference``). ``:registry: myapp.static_components.registry`` documents a
component from that registry instead of ``built_in_registry``. Nothing is rendered, so the docs
build needs no Django settings. An unknown component fails the build.

The extension is not part of the alliance-platform-ui package. Add this directory to ``sys.path``
and ``ap_ui_components`` to ``extensions``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ap_ui_component_reference import component_reference_rst
from ap_ui_component_reference import describe_component
from ap_ui_component_reference import load_registry
from docutils import nodes
from docutils.parsers.rst import directives
from docutils.statemachine import StringList
from sphinx.application import Sphinx
from sphinx.config import Config
from sphinx.errors import ExtensionError
from sphinx.util.docutils import SphinxDirective

#: Holds the stylesheet that lets the prop tables' cells wrap
_STATIC_DIR = Path(__file__).parent / "ap_ui_components_static"


class UIComponentDirective(SphinxDirective):
    """``.. ui-component:: <name>``, with an optional ``:registry: <module.attribute>``."""

    required_arguments = 1
    option_spec = {"registry": directives.unchanged_required}

    def run(self) -> list[nodes.Node]:
        name = self.arguments[0]
        try:
            registry = load_registry(self.options["registry"]) if "registry" in self.options else None
            reference = describe_component(name, registry)
        except (ImportError, LookupError, ValueError) as exc:
            # A warning would not fail a build without -W
            raise ExtensionError(f"{self.get_location()}: ui-component: {exc}") from exc
        # Read the page again when the renderer changes, as Sphinx cannot see that the output
        # depends on it
        for source_file in reference.source_files:
            self.env.note_dependency(source_file)
        # The ttag role exists where the docs register the templatetag object type, as this
        # repository's conf.py does
        link_react_tag = "ttag" in self.env.get_domain("std").roles
        lines = component_reference_rst(reference, link_react_tag=link_react_tag)
        container = nodes.container()
        self.state.nested_parse(StringList(lines, source=f"<ui-component {name}>"), 0, container)
        return list(container.children)


def _add_static_path(app: Sphinx, config: Config) -> None:
    # conf.py may set a tuple
    config.html_static_path = [*config.html_static_path, str(_STATIC_DIR)]


def setup(app: Sphinx) -> dict[str, Any]:
    app.add_directive("ui-component", UIComponentDirective)
    app.connect("config-inited", _add_static_path)
    app.add_css_file("ap_ui_components.css")
    return {"parallel_read_safe": True, "parallel_write_safe": True}
