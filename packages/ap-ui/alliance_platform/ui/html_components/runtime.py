"""Browser runtimes for static components.

A component that needs JavaScript marks its root with :func:`add_auto_attach_marker` and lists
:func:`resolve_static_runtime_resource` in ``resolve_component_resources()``. The resource is the
``@alliancesoftware/ui`` static runtime entry: it registers the runtime of each built-in component,
loads a runtime only when the page has a root marked with its token, and attaches it to those
roots. The asset context embeds the entry once per page, whatever the number of components.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from django.template import TemplateSyntaxError

if TYPE_CHECKING:
    from .base import BaseHtmlUIComponentRenderer

#: The self-executing entry that registers the built-in runtimes and attaches the marked roots
STATIC_RUNTIME_MODULE_PATH = "@alliancesoftware/ui/static-runtime.auto.ts"
#: The extensions tried when resolving the entry
STATIC_RUNTIME_RESOLVE_EXTENSIONS = [".ts", ".tsx", ".js", ".mjs"]


def resolve_static_runtime_resource(renderer: BaseHtmlUIComponentRenderer) -> FrontendResource:
    """Resolve the static runtime entry the way ``renderer`` resolves its other resources.

    Raises ``TemplateSyntaxError`` when the installed ``@alliancesoftware/ui`` does not have it.
    """

    try:
        return renderer.resolve_frontend_resource(
            STATIC_RUNTIME_MODULE_PATH,
            resolve_extensions=STATIC_RUNTIME_RESOLVE_EXTENSIONS,
        )
    except TemplateSyntaxError as exc:
        raise TemplateSyntaxError(
            f"The static '{renderer.name}' component requires '{STATIC_RUNTIME_MODULE_PATH}'. "
            "Upgrade @alliancesoftware/ui to a compatible version."
        ) from exc


def add_auto_attach_marker(root_attrs: dict[str, Any], runtime_name: str) -> None:
    """Mark a static component root for the runtime registered under ``runtime_name``.

    The value is a token list so a root can opt into more than one small runtime without one
    renderer overwriting another marker.
    """

    tokens = str(root_attrs.get("data-apui-attach") or "").split()
    if runtime_name not in tokens:
        tokens.append(runtime_name)
    root_attrs["data-apui-attach"] = " ".join(tokens)
