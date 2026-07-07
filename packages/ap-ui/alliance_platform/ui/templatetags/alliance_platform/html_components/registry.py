from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import Iterable
from typing import TypeVar

if TYPE_CHECKING:
    from .base import BaseHtmlUIComponentRenderer

RendererType = TypeVar("RendererType", bound="BaseHtmlUIComponentRenderer")


@dataclass(frozen=True)
class HtmlUIComponentSpec:
    name: str
    renderer_cls: type["BaseHtmlUIComponentRenderer"]


class HtmlUIComponentRegistry:
    def __init__(self):
        self._specs: OrderedDict[str, HtmlUIComponentSpec] = OrderedDict()

    def register(self, spec: HtmlUIComponentSpec):
        self._specs[spec.name] = spec

    def register_renderer(self, name: str, renderer_cls: type["BaseHtmlUIComponentRenderer"]):
        self.register(HtmlUIComponentSpec(name=name, renderer_cls=renderer_cls))

    def get(self, name: str) -> HtmlUIComponentSpec | None:
        return self._specs.get(name)

    def exists(self, name: str) -> bool:
        return name in self._specs

    def list_names(self) -> list[str]:
        return list(self._specs.keys())

    def list_specs(self) -> Iterable[HtmlUIComponentSpec]:
        return self._specs.values()


built_in_registry = HtmlUIComponentRegistry()


# Keep the default built-ins close to registry construction so parsing validation can rely on them.
from .components.button import UIButtonRenderer  # noqa: E402
from .components.button_group import UIButtonGroupRenderer  # noqa: E402
from .components.input import UINumberInputRenderer  # noqa: E402
from .components.input import UITextAreaRenderer  # noqa: E402
from .components.input import UITextInputRenderer  # noqa: E402
from .components.table import UITableBodyRenderer  # noqa: E402
from .components.table import UITableCellRenderer  # noqa: E402
from .components.table import UITableColumnRenderer  # noqa: E402
from .components.table import UITableHeaderRenderer  # noqa: E402
from .components.table import UITableRenderer  # noqa: E402
from .components.table import UITableRowRenderer  # noqa: E402

built_in_registry.register_renderer("button", UIButtonRenderer)
built_in_registry.register_renderer("button_group", UIButtonGroupRenderer)
built_in_registry.register_renderer("text_input", UITextInputRenderer)
built_in_registry.register_renderer("number_input", UINumberInputRenderer)
built_in_registry.register_renderer("text_area", UITextAreaRenderer)
built_in_registry.register_renderer("table", UITableRenderer)
built_in_registry.register_renderer("table_header", UITableHeaderRenderer)
built_in_registry.register_renderer("table_body", UITableBodyRenderer)
built_in_registry.register_renderer("table_column", UITableColumnRenderer)
built_in_registry.register_renderer("table_row", UITableRowRenderer)
built_in_registry.register_renderer("table_cell", UITableCellRenderer)
