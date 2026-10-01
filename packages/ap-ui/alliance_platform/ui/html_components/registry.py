from __future__ import annotations

import re

from .base import BaseHtmlUIComponentRenderer

_COMPONENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class HtmlUIComponentRegistry:
    """Maps ``{% ui %}`` component names to their renderer classes."""

    def __init__(self):
        self._renderers: dict[str, type[BaseHtmlUIComponentRenderer]] = {}

    def register_renderer(
        self,
        name: str,
        renderer_cls: type[BaseHtmlUIComponentRenderer],
        *,
        replace: bool = False,
    ):
        """Register ``renderer_cls`` as the renderer for ``{% ui "<name>" %}``.

        ``name`` must be snake_case and equal to ``renderer_cls.name``, so warnings, generated ids
        and the registry all use one name. Registering a different renderer under a name that is
        already taken raises ``ValueError`` unless ``replace=True``; registering the same renderer
        again is a no-op.
        """
        if not isinstance(name, str) or not _COMPONENT_NAME_RE.fullmatch(name):
            raise ValueError(
                f"Invalid ui component name {name!r}: use snake_case (lowercase letters, digits and "
                "underscores, starting with a letter)"
            )
        if not isinstance(renderer_cls, type) or not issubclass(renderer_cls, BaseHtmlUIComponentRenderer):
            raise TypeError(f"Renderer for ui component '{name}' must subclass BaseHtmlUIComponentRenderer")
        renderer_name = getattr(renderer_cls, "name", None)
        if renderer_name != name:
            raise ValueError(
                f"Cannot register {renderer_cls.__name__} as ui component '{name}': its name attribute "
                f"is {renderer_name!r}. Set name = {name!r} on the renderer class."
            )
        existing = self._renderers.get(name)
        if existing is not None and existing is not renderer_cls and not replace:
            raise ValueError(
                f"ui component '{name}' is already registered to {existing.__name__}; pass "
                "replace=True to replace it"
            )
        self._renderers[name] = renderer_cls

    def get(self, name: str) -> type[BaseHtmlUIComponentRenderer] | None:
        return self._renderers.get(name)

    def exists(self, name: str) -> bool:
        return name in self._renderers

    def list_names(self) -> list[str]:
        return list(self._renderers)


#: The registry ``{% ui %}`` uses unless ``parse_ui_tag`` is given another one. Holds the built-in
#: renderers and any added with :func:`register_component`.
built_in_registry = HtmlUIComponentRegistry()


def register_component(
    name: str,
    renderer_cls: type[BaseHtmlUIComponentRenderer],
    *,
    replace: bool = False,
):
    """Register a static renderer so templates can use it as ``{% ui "<name>" %}``.

    Call this from your ``AppConfig.ready()``. ``{% ui %}`` looks components up when a template
    compiles, so a component registered after a template compiled is unknown to that template.

    Args:
        name: The snake_case component name used in templates. Must equal ``renderer_cls.name``.
        renderer_cls: The renderer, a subclass of
            :class:`~alliance_platform.ui.html_components.base.BaseHtmlUIComponentRenderer`.
        replace: Replace a different renderer already registered under ``name`` (including a
            built-in) instead of raising ``ValueError``.
    """
    built_in_registry.register_renderer(name, renderer_cls, replace=replace)


# Keep the default built-ins close to registry construction so parsing validation can rely on them.
from .components.button import UIButtonRenderer  # noqa: E402
from .components.button_group import UIButtonGroupRenderer  # noqa: E402
from .components.icon import UIIconRenderer  # noqa: E402
from .components.inline_alert import UIInlineAlertRenderer  # noqa: E402
from .components.input import UINumberInputRenderer  # noqa: E402
from .components.input import UITextAreaRenderer  # noqa: E402
from .components.input import UITextInputRenderer  # noqa: E402
from .components.layout import UIContentRenderer  # noqa: E402
from .components.layout import UIFooterRenderer  # noqa: E402
from .components.layout import UIHeaderRenderer  # noqa: E402
from .components.layout import UIHeadingRenderer  # noqa: E402
from .components.menubar import UIMenubarItemRenderer  # noqa: E402
from .components.menubar import UIMenubarRenderer  # noqa: E402
from .components.menubar import UIMenubarSectionRenderer  # noqa: E402
from .components.menubar import UIMenubarSubMenuRenderer  # noqa: E402
from .components.pagination import UIPaginationRenderer  # noqa: E402
from .components.table import UITableBodyRenderer  # noqa: E402
from .components.table import UITableCellRenderer  # noqa: E402
from .components.table import UITableColumnRenderer  # noqa: E402
from .components.table import UITableHeaderRenderer  # noqa: E402
from .components.table import UITableRenderer  # noqa: E402
from .components.table import UITableRowRenderer  # noqa: E402

register_component("button", UIButtonRenderer)
register_component("button_group", UIButtonGroupRenderer)
register_component("icon", UIIconRenderer)
register_component("text_input", UITextInputRenderer)
register_component("number_input", UINumberInputRenderer)
register_component("text_area", UITextAreaRenderer)
register_component("inline_alert", UIInlineAlertRenderer)
register_component("content", UIContentRenderer)
register_component("heading", UIHeadingRenderer)
register_component("header", UIHeaderRenderer)
register_component("footer", UIFooterRenderer)
register_component("pagination", UIPaginationRenderer)
register_component("table", UITableRenderer)
register_component("table_header", UITableHeaderRenderer)
register_component("table_body", UITableBodyRenderer)
register_component("table_column", UITableColumnRenderer)
register_component("table_row", UITableRowRenderer)
register_component("table_cell", UITableCellRenderer)
register_component("menubar", UIMenubarRenderer)
register_component("menubar_item", UIMenubarItemRenderer)
register_component("menubar_submenu", UIMenubarSubMenuRenderer)
register_component("menubar_section", UIMenubarSectionRenderer)
