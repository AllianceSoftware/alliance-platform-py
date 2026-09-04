from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseHtmlUIComponentRenderer


class HtmlUIComponentRegistry:
    def __init__(self):
        self._renderers: dict[str, type["BaseHtmlUIComponentRenderer"]] = {}

    def register_renderer(self, name: str, renderer_cls: type["BaseHtmlUIComponentRenderer"]):
        self._renderers[name] = renderer_cls

    def get(self, name: str) -> type["BaseHtmlUIComponentRenderer"] | None:
        return self._renderers.get(name)

    def exists(self, name: str) -> bool:
        return name in self._renderers

    def list_names(self) -> list[str]:
        return list(self._renderers)


built_in_registry = HtmlUIComponentRegistry()


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

built_in_registry.register_renderer("button", UIButtonRenderer)
built_in_registry.register_renderer("button_group", UIButtonGroupRenderer)
built_in_registry.register_renderer("icon", UIIconRenderer)
built_in_registry.register_renderer("text_input", UITextInputRenderer)
built_in_registry.register_renderer("number_input", UINumberInputRenderer)
built_in_registry.register_renderer("text_area", UITextAreaRenderer)
built_in_registry.register_renderer("inline_alert", UIInlineAlertRenderer)
built_in_registry.register_renderer("content", UIContentRenderer)
built_in_registry.register_renderer("heading", UIHeadingRenderer)
built_in_registry.register_renderer("header", UIHeaderRenderer)
built_in_registry.register_renderer("footer", UIFooterRenderer)
built_in_registry.register_renderer("pagination", UIPaginationRenderer)
built_in_registry.register_renderer("table", UITableRenderer)
built_in_registry.register_renderer("table_header", UITableHeaderRenderer)
built_in_registry.register_renderer("table_body", UITableBodyRenderer)
built_in_registry.register_renderer("table_column", UITableColumnRenderer)
built_in_registry.register_renderer("table_row", UITableRowRenderer)
built_in_registry.register_renderer("table_cell", UITableCellRenderer)
built_in_registry.register_renderer("menubar", UIMenubarRenderer)
built_in_registry.register_renderer("menubar_item", UIMenubarItemRenderer)
built_in_registry.register_renderer("menubar_submenu", UIMenubarSubMenuRenderer)
built_in_registry.register_renderer("menubar_section", UIMenubarSectionRenderer)
