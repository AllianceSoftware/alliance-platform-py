from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal
from html.parser import HTMLParser
import re
from typing import Any

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from alliance_platform.ui.icons import get_static_icon_resource
from django.template import Context
from django.utils.functional import Promise
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from ..base import build_attrs_string
from .input import LabeledInputState
from .input import UITextInputBaseRenderer

_NATIVE_SELECT_STYLE_PATH = "@alliancesoftware/ui/components/select/NativeSelect.css.ts"
_CHEVRON_DOWN_ICON = "ChevronDownOutlined"

# The props of NativeSelect that only make sense with React
_NATIVE_SELECT_REACT_ONLY_PROPS = frozenset({"inputRef", "containerRef", "labelRef"})
# Props of the other inputs that a select does not have: it has no placeholder or read-only state
_NOT_SELECT_PROPS = ("placeholder", "isReadOnly", "readOnly")

_ASCII_WHITESPACE = "\t\n\f\r "
_ASCII_WHITESPACE_RE = re.compile(f"[{_ASCII_WHITESPACE}]+")
# Tags that end the text of an option without an end tag
_OPTION_TEXT_ENDING_TAGS = frozenset({"option", "optgroup", "select", "hr"})


@dataclass
class _OptionTag:
    """An ``<option>`` start tag in a select's children markup."""

    #: Where the tag starts, as ``HTMLParser.getpos()`` gives it: a line number and the column on it
    position: tuple[int, int]
    #: The tag as written
    source: str
    attrs: list[tuple[str, str | None]]
    text: list[str] = field(default_factory=list)

    @property
    def is_selected(self) -> bool:
        return any(name == "selected" for name, _ in self.attrs)

    @property
    def value(self) -> str:
        """The value the option submits: its ``value`` attribute, or else its text."""
        for name, value in self.attrs:
            if name == "value":
                return value or ""
        return _ASCII_WHITESPACE_RE.sub(" ", "".join(self.text)).strip(_ASCII_WHITESPACE)


class _OptionFinder(HTMLParser):
    """Finds the ``<option>`` start tags in markup, with the text of the options it needs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.options: list[_OptionTag] = []
        self._text_option: _OptionTag | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _OPTION_TEXT_ENDING_TAGS:
            self._text_option = None
        if tag != "option":
            return
        option = _OptionTag(position=self.getpos(), source=self.get_starttag_text() or "", attrs=attrs)
        self.options.append(option)
        if not any(name == "value" for name, _ in attrs):
            self._text_option = option

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # An option is not a void element, so a browser ignores the slash
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in _OPTION_TEXT_ENDING_TAGS:
            self._text_option = None

    def handle_data(self, data: str) -> None:
        if self._text_option is not None:
            self._text_option.text.append(data)


def _select_options(options_html: str, values: Collection[str]) -> str:
    """Return ``options_html`` with exactly the options whose value is in ``values`` selected.

    Only the start tags of the options whose selection changes are rewritten; the rest of the
    markup is left as written.
    """
    finder = _OptionFinder()
    finder.feed(options_html)
    finder.close()
    line_starts = [0, *(match.end() for match in re.finditer("\n", options_html))]
    parts: list[str] = []
    cursor = 0
    for option in finder.options:
        is_selected = option.value in values
        if is_selected == option.is_selected:
            continue
        line, column = option.position
        start = line_starts[line - 1] + column
        attrs: dict[str, Any] = {
            name: True if value is None else value for name, value in option.attrs if name != "selected"
        }
        attrs["selected"] = is_selected
        parts += [options_html[cursor:start], f"<option{build_attrs_string(attrs)}>"]
        cursor = start + len(option.source)
    parts.append(options_html[cursor:])
    return "".join(parts)


def _is_value_item(value: Any) -> bool:
    return isinstance(value, (str, int, float, Decimal, Promise)) or value is None


def _option_value(value: Any) -> str:
    # As Django's ChoiceWidget compares a value with its options
    return "" if value is None else str(value)


class UISelectRenderer(UITextInputBaseRenderer):
    """Renders a native ``<select>`` in the chrome of a text input, mirroring ``NativeSelect.tsx``.

    The children are the ``<option>`` and ``<optgroup>`` elements, rendered as written, as React
    renders the elements passed as a select's children. A ``value`` (or ``defaultValue``) selects
    the options it names and no others, as React marks the options of a select with a value: the
    value of an option is its ``value`` attribute, or its text when it has none. Without one the
    options' own ``selected`` attributes stand, as Django's select widget writes them.
    """

    name = "select"
    react_tag = 'component "@alliancesoftware/ui" "NativeSelect"'
    # The options are the children
    has_children = True
    control_tag = "select"
    # Django's SelectMultiple widget sets the native multiple attribute
    prop_aliases = {"multiple": "isMultiple"}
    unsupported_prop_reasons = {
        key: "React-only props are not supported by static input components"
        for key in _NATIVE_SELECT_REACT_ONLY_PROPS
    }
    handled_props = (UITextInputBaseRenderer.handled_props - set(_NOT_SELECT_PROPS)) | {"isMultiple"}
    control_pass_through_props = frozenset(
        {"autoComplete", "autoFocus", "tabIndex", "form", "dir", "lang", "title", "size"}
    )
    prop_docs = {
        "id": UITextInputBaseRenderer.prop_docs["id"],
        "required": UITextInputBaseRenderer.prop_docs["required"],
        "addonBefore": UITextInputBaseRenderer.prop_docs["addonBefore"],
        "addonAfter": UITextInputBaseRenderer.prop_docs["addonAfter"],
        "isMultiple": "``multiple`` is the attribute Django's ``SelectMultiple`` widget sets.",
        "value": (
            "The value of the option to select, or a list of values for a multiple select: the options "
            "it names are marked ``selected`` and the others are not, as React marks them. Without "
            "``value`` or ``default_value`` the options' own ``selected`` attributes stand."
        ),
        "defaultValue": "The same as ``value``: a server-rendered select has no controlled value.",
    }

    def resolve_component_resources(self) -> list[FrontendResource]:
        return [
            *super().resolve_component_resources(),
            self.resolve_frontend_resource(_NATIVE_SELECT_STYLE_PATH),
            get_static_icon_resource(_CHEVRON_DOWN_ICON, origin=self.origin),
        ]

    def allow_non_scalar_prop(self, key: str, value: Any) -> bool:
        if key in ("value", "defaultValue") and isinstance(value, (list, tuple)):
            return all(_is_value_item(item) for item in value)
        return super().allow_non_scalar_prop(key, value)

    def is_list_box(self, props: dict[str, Any]) -> bool:
        """Whether the select shows more than one row, so it has no chevron, as in React."""
        if props.get("isMultiple"):
            return True
        try:
            return float(props.get("size") or 1) > 1
        except (TypeError, ValueError):
            return False

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        # The inputs' rendering reads these before it reports the props a control does not take
        for key in _NOT_SELECT_PROPS:
            if key in props:
                self.report(
                    f"Prop '{key}' is not a supported '{self.name}' attribute and will be ignored",
                    kind="contract",
                )
        props = {key: value for key, value in props.items() if key not in _NOT_SELECT_PROPS}
        # The options render inside the select, as React passes its children to the select
        return super().render_component(context, {**props, "children": children_html}, children_html)

    def render_control(
        self,
        context: Context,
        props: dict[str, Any],
        state: LabeledInputState,
        text_input_base_styles: Any,
    ) -> str:
        select_styles = self.resolve_vanilla_extract_mapping(_NATIVE_SELECT_STYLE_PATH)
        attrs: dict[str, Any] = {
            **self.get_base_control_attrs(props, state, text_input_base_styles),
            "multiple": bool(props.get("isMultiple")),
            "className": self.join_classes(
                self.get_style_class(text_input_base_styles, "input"),
                self.get_style_class(select_styles, "select"),
                props.get("inputClassName"),
            ),
        }
        options_html = self.select_options(props, str(props.get("children") or ""))
        return mark_safe(f"<select{self.build_attrs_string(attrs)}>{options_html}</select>")

    def select_options(self, props: dict[str, Any], options_html: str) -> str:
        """Select the options ``value`` (or ``defaultValue``) names in ``options_html``."""
        key = "value" if props.get("value") is not None else "defaultValue"
        value = props.get(key)
        if value is None:
            return options_html
        values = list(value) if isinstance(value, (list, tuple)) else [value]
        if len(values) > 1 and not props.get("isMultiple"):
            # React selects them all, and the browser shows the last
            self.report(f"Prop '{key}' must be a single value unless 'isMultiple' is set", kind="contract")
        return _select_options(options_html, {_option_value(item) for item in values})

    def render_adornments(
        self, props: dict[str, Any], state: LabeledInputState, text_input_base_styles: Any
    ) -> str:
        # The icons sit together over the end of the select, out of the input wrapper's slots
        select_styles = self.resolve_vanilla_extract_mapping(_NATIVE_SELECT_STYLE_PATH)
        icons: list[str] = []
        if self.should_render_validation_icon(props, state):
            icons.append(
                self.render_validation_icon(
                    state, [self.get_style_class(text_input_base_styles, "validationIcon")]
                )
            )
        if not self.is_list_box(props):
            icons.append(
                self.render_icon(
                    _CHEVRON_DOWN_ICON,
                    "xs",
                    [self.get_style_class(select_styles, "chevron")],
                    slot=False,
                )
            )
        if not icons:
            return ""
        adornments_class = self.get_style_class(select_styles, "adornments")
        return f'<span class="{conditional_escape(adornments_class)}">{"".join(icons)}</span>'
