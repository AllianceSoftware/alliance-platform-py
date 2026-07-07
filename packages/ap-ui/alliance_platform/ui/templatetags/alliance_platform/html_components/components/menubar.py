"""Static HTML renderers for the Alliance UI menubar components.

These mirror ``@alliancesoftware/ui``'s ``Menubar`` (see ``components/menu-bar/Menubar.tsx``) for
server-rendered navigation menus: the same markup structure, vanilla-extract classes and state
data attributes, with interactivity provided by a small standalone runtime
(``Menubar.attach.ts``) rather than React. Links are real anchors and form actions are real
buttons, so navigation and submission work without JavaScript; the runtime only adds menu
open/close and keyboard behaviour.

Client-side selection state, dynamic collections (``items``), callbacks (``onAction``) and width
overflow into a "More" submenu are intentionally unsupported.

Cross-component coordination (visible child counting for empty pruning, current-item propagation,
roving tab stop assignment) is done through a :class:`MenubarRenderState` stack stored in
``context.render_context``, which survives ``{% include %}`` within a single template render.
Renderer instances are template nodes shared between renders and must not hold per-render state.

Static extensions over the React output (all removed by the parity fixture normalisation and
covered by unit tests instead):

- Empty submenus/sections are pruned after permission checks (``url_with_perm`` denials raise
  :class:`~alliance_platform.frontend.templatetags.react.OmitComponentFromRendering`).
- Closed submenu popups are rendered hidden in place (React renders them in a portal only while
  open) and are marked with ``data-apui-menu-popover``/``data-apui-menu-popup`` for the runtime.
- The root exposes the ``isOpen``/``isFocused``/popover-``isOpen`` class names through
  ``data-*-class`` attributes so the runtime can toggle them without importing the CSS mapping.
- ``data-current`` marks current items and their ancestors.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import field
from decimal import Decimal
import html as html_module
import re
from typing import Any
from typing import Iterator
from typing import Literal
from typing import Mapping
import warnings

from django.template import Context
from django.utils.functional import Promise
from django.utils.html import conditional_escape
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource

from ..base import ICON_STYLE_PATH
from ..base import BaseHtmlUIComponentRenderer
from ..base import to_html_attr_name
from ..content import render_content
from ..runtime import attach_module_script

_MENUBAR_STYLE_PATH = "@alliancesoftware/ui/components/menu-bar/Menubar.css.ts"
_POPOVER_STYLE_PATH = "@alliancesoftware/ui/components/overlay/Popover.css.ts"
# The runtime module is optional during resource resolution; if unresolved rendering degrades
# gracefully to static HTML without script output.
_RUNTIME_MODULE_PATH = "@alliancesoftware/ui/components/menu-bar/Menubar.attach.ts"

# Key used in ``context.render_context`` for the stack of in-progress menubar renders.
_MENUBAR_STATE_KEY = "alliance_platform_ui_menubar_state"
# Key used in ``context.render_context`` to keep generated ids unique within a template render.
# Shared with the input components so ids never collide within one render.
_HTML_ID_COUNTER_KEY = "alliance_platform_ui_html_id_counter"

VALID_LAYOUTS = ("horizontal", "vertical", "inline")
VALID_ITEM_ELEMENT_TYPES = ("a", "button", "div")

# SVG paths matching @alliancesoftware/icons/outlined/Chevron{Down,Right,Up}Outlined.tsx
_CHEVRON_DOWN_SVG_PATH = "M6 9L12 15L18 9"
_CHEVRON_RIGHT_SVG_PATH = "M9 18L15 12L9 6"
_CHEVRON_UP_SVG_PATH = "M18 15L12 9L6 15"

# Matches event handler props in any of the forms they can reach us in after prop normalization
# (onClick, onclick, on_click -> onClick). These must never be rendered: a string value would
# become a live inline event handler attribute, which React never renders.
_EVENT_HANDLER_PROP_RE = re.compile(r"^on[A-Za-z]")

_EVENT_HANDLER_REASON = "event handlers are not supported by static menubar components"
_CALLBACK_REASON = "client-side action callbacks are not supported by static menubar components"
_COLLECTION_REASON = "collection render props are not supported by static menubar components"
_SELECTION_REASON = "selection is not supported by static menubar components yet"
_OVERFLOW_REASON = "width overflow handling is not supported by static menubar components yet"

_MENUBAR_UNSUPPORTED_PROPS: Mapping[str, str] = {
    "items": _COLLECTION_REASON,
    "onAction": _CALLBACK_REASON,
    "selectionMode": _SELECTION_REASON,
    "selectionBehavior": _SELECTION_REASON,
    "selectedKeys": _SELECTION_REASON,
    "defaultSelectedKeys": _SELECTION_REASON,
    "onSelectionChange": _SELECTION_REASON,
    "disabledKeys": "pass 'is_disabled' on the child components instead",
    "expandedKeys": (
        "controlled expansion state is not supported by static menubar components; "
        "pass 'default_expanded_keys' for initial open state"
    ),
    "onExpandedChange": _CALLBACK_REASON,
    "itemElementType": "custom item element types are not supported by static menubar components",
    "overflowLabel": _OVERFLOW_REASON,
    "overflowTextLabel": _OVERFLOW_REASON,
    "closeOnSelect": "close-on-select behaviour is not configurable for static menubar components",
}


def _is_scalar_prop_value(value: Any) -> bool:
    # Promise covers lazy translation proxies (e.g. gettext_lazy labels), which render like plain
    # strings. Decimal covers Django DecimalField values.
    return isinstance(value, (str, int, float, bool, Decimal, Promise)) or value is None


def _extract_css_var_name(value: str) -> str | None:
    """Extract the custom property name from a serialized theme var reference.

    The vanilla-extract mapping serializes ``createVar`` values as ``var(--name)`` references (the
    same values ``assignInlineVars`` accepts in the React implementation).
    """
    match = re.fullmatch(r"var\((--[^,)]+)(?:,.*)?\)", value.strip())
    if match:
        return match.group(1)
    if value.startswith("--"):
        return value
    return None


@dataclass
class MenubarRenderFrame:
    """Bookkeeping for one menu grouping: the root menu, a submenu popup or a section."""

    #: nesting depth used for ``data-level``; sections share their parent's level
    level: int
    #: number of visible children rendered so far (items, submenus and sections each count once)
    item_count: int = 0
    #: True when any rendered child (or descendant, via propagation) is marked current
    contains_current: bool = False


@dataclass
class MenubarRenderState:
    layout: Literal["horizontal", "vertical", "inline"]
    orientation: Literal["horizontal", "vertical"]
    should_focus_wrap: bool
    default_focused_key: str | None
    #: submenu keys rendered in the open state (``default_expanded_keys`` prop)
    expanded_keys: frozenset[str]
    frame_stack: list[MenubarRenderFrame] = field(default_factory=list)
    #: True once a root-level item has claimed ``tabindex="0"`` for the roving tabindex
    has_tab_stop: bool = False

    @property
    def current_frame(self) -> MenubarRenderFrame:
        return self.frame_stack[-1]


def get_current_menubar_state(context: Context) -> MenubarRenderState | None:
    stack = context.render_context.get(_MENUBAR_STATE_KEY)
    if not stack:
        return None
    return stack[-1]


@contextmanager
def _push_menubar_state(context: Context, state: MenubarRenderState) -> Iterator[None]:
    stack = context.render_context.get(_MENUBAR_STATE_KEY)
    if stack is None:
        stack = []
        context.render_context[_MENUBAR_STATE_KEY] = stack
    stack.append(state)
    try:
        yield
    finally:
        stack.pop()


@contextmanager
def _push_menubar_frame(state: MenubarRenderState, frame: MenubarRenderFrame) -> Iterator[None]:
    state.frame_stack.append(frame)
    try:
        yield
    finally:
        state.frame_stack.pop()


class UIMenubarComponentRendererBase(BaseHtmlUIComponentRenderer):
    """Shared prop validation for the static menubar component renderers.

    Mirrors the input/table renderer policy: event handler props and React-only props warn and are
    dropped, unknown props warn rather than rendering arbitrary attributes, and ``data-*``/
    ``aria-*`` attributes pass through only where the component contract allows them.
    """

    #: registered dispatcher name, used in warning messages
    component_name: str
    #: props (after normalization) the component understands
    supported_props: frozenset[str] = frozenset()
    #: props rejected with a specific reason instead of the generic unknown-prop warning
    unsupported_prop_reasons: Mapping[str, str] = {}
    #: prop name aliases applied after normalization (e.g. ``disabled`` -> ``isDisabled``)
    prop_aliases: Mapping[str, str] = {}
    #: whether arbitrary data-* attributes pass through to the rendered element
    allow_data_props = True
    #: whether arbitrary aria-* attributes pass through to the rendered element
    allow_aria_props = True
    #: aria-* attribute names allowed even when allow_aria_props is False
    extra_allowed_aria_props: frozenset[str] = frozenset()
    #: supported props that may hold non-scalar values
    non_scalar_props: frozenset[str] = frozenset()

    def resolve_props(self, context: Context) -> dict[str, Any]:
        return self.filter_component_props(super().resolve_props(context))

    def filter_component_props(self, props: dict[str, Any]) -> dict[str, Any]:
        filtered: dict[str, Any] = {}
        for key, value in props.items():
            key = self.prop_aliases.get(key, key)
            if value is None:
                # Treat None the same as an unset prop, mirroring undefined in JSX
                continue
            reason = self.unsupported_prop_reasons.get(key)
            if reason:
                warnings.warn(f"Prop '{key}' will be ignored: {reason}")
                continue
            if _EVENT_HANDLER_PROP_RE.match(key):
                warnings.warn(f"Prop '{key}' will be ignored: {_EVENT_HANDLER_REASON}")
                continue
            attr_name = to_html_attr_name(key)
            if attr_name.startswith("data-") or attr_name.startswith("aria-"):
                allowed = self.allow_data_props if attr_name.startswith("data-") else self.allow_aria_props
                if not allowed and attr_name not in self.extra_allowed_aria_props:
                    warnings.warn(
                        f"Prop '{key}' is not supported on '{self.component_name}' and will be ignored"
                    )
                    continue
                if not _is_scalar_prop_value(value):
                    warnings.warn(
                        f"Prop '{key}' with non-scalar value is not supported by static menubar "
                        "components and will be ignored"
                    )
                    continue
                filtered[attr_name] = value
                continue
            if key not in self.supported_props:
                warnings.warn(
                    f"Prop '{key}' is not a supported '{self.component_name}' prop and will be ignored"
                )
                continue
            if key == "style":
                if not isinstance(value, (str, dict)):
                    warnings.warn("Prop 'style' must be a string or dict; it will be ignored")
                    continue
            elif not _is_scalar_prop_value(value) and key not in self.non_scalar_props:
                warnings.warn(
                    f"Prop '{key}' with non-scalar value is not supported by static menubar "
                    "components and will be ignored"
                )
                continue
            filtered[key] = value
        return filtered

    def resolve_menubar_styles(self) -> Any:
        return self.resolve_vanilla_extract_mapping(_MENUBAR_STYLE_PATH)

    def collect_data_aria_attrs(self, props: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value for key, value in props.items() if key.startswith("data-") or key.startswith("aria-")
        }

    def generate_html_id(self, context: Context, prefix: str) -> str:
        """Generate a deterministic id, unique within the current template render."""
        render_context = context.render_context
        counter = (render_context.get(_HTML_ID_COUNTER_KEY) or 0) + 1
        render_context[_HTML_ID_COUNTER_KEY] = counter
        return f"{prefix}-{counter}"

    def get_state_or_warn(self, context: Context) -> MenubarRenderState | None:
        state = get_current_menubar_state(context)
        if state is None:
            warnings.warn(
                f"'{self.component_name}' was rendered outside of a '{{% ui \"menubar\" %}}' component; "
                "rendering fallback markup"
            )
        return state

    def make_fallback_state(self) -> MenubarRenderState:
        return MenubarRenderState(
            layout="horizontal",
            orientation="horizontal",
            should_focus_wrap=True,
            default_focused_key=None,
            expanded_keys=frozenset(),
            frame_stack=[MenubarRenderFrame(level=0)],
        )

    def resolve_key(self, props: dict[str, Any]) -> str | None:
        key = props.get("key")
        return str(key) if key is not None else None

    def resolve_text_value(
        self,
        props: dict[str, Any],
        content_html: str,
        *,
        content_description: str,
    ) -> str | None:
        """Resolve the accessible text label, deriving it from plain text content when possible.

        Mirrors react-stately collection behaviour: an explicit ``textValue`` wins, plain text
        content is used directly, and rich content without a ``textValue`` warns because typeahead
        and ``aria-label`` need a text label. For rich content the tag-stripped text is still used
        as a best-effort fallback.
        """
        text_value = props.get("textValue")
        if text_value is not None:
            return str(text_value)
        aria_label = props.get("aria-label")
        stripped = content_html.strip()
        if "<" not in stripped:
            derived = " ".join(html_module.unescape(stripped).split())
            return derived or (str(aria_label) if aria_label is not None else None)
        if aria_label is not None:
            return str(aria_label)
        warnings.warn(
            f"'{self.component_name}' has non-plain-text {content_description}; pass 'text_value' "
            "so it has an accessible label"
        )
        derived = " ".join(html_module.unescape(strip_tags(content_html)).split())
        return derived or None

    def wrap_plain_text_content(self, content_html: str) -> str:
        """Wrap plain text content in a ``<span>``, matching React's ``Text`` wrapping."""
        stripped = content_html.strip()
        if not stripped:
            return ""
        if "<" in stripped:
            return content_html
        return f"<span>{stripped}</span>"

    def claim_tab_index(self, state: MenubarRenderState | None, key: str | None, is_disabled: bool) -> int:
        """Assign the roving tabindex tab stop for root-level menu items.

        ``defaultFocusedKey`` claims the tab stop when set (and visible); otherwise the first
        enabled root item does. Everything else gets ``tabindex="-1"`` and the runtime moves the
        tab stop as focus roves.
        """
        if state is None or state.current_frame.level != 0 or is_disabled or state.has_tab_stop:
            return -1
        if state.default_focused_key is not None and key != state.default_focused_key:
            return -1
        state.has_tab_stop = True
        return 0

    def track_rendered_child(self, state: MenubarRenderState | None, is_current: bool):
        if state is None:
            return
        frame = state.current_frame
        frame.item_count += 1
        if is_current:
            frame.contains_current = True

    def resolve_is_current(self, props: dict[str, Any]) -> tuple[bool, str | None]:
        """Resolve the current marker and the ``aria-current`` value to render."""
        is_current_prop = bool(props.get("isCurrent"))
        aria_current = props.get("aria-current")
        if aria_current in (False, "false"):
            aria_current = None
        if is_current_prop and aria_current is None:
            aria_current = "page"
        if aria_current is True:
            aria_current = "true"
        is_current = is_current_prop or bool(aria_current)
        return is_current, str(aria_current) if aria_current is not None else None

    def render_menu_item_element(
        self,
        *,
        element_type: str,
        attrs: dict[str, Any],
        content_attrs: dict[str, Any],
        content_html: str,
        chevron_html: str = "",
    ) -> str:
        """Render the interactive menu item element with the shared content wrapper structure.

        The plain ``<div>`` wrapper matches the React implementation (it holds the selected-state
        icon when selection is supported; without selection it renders without a class).
        """
        children = f"<div><span{self.build_attrs_string(content_attrs)}>{content_html}</span></div>"
        return self._render_tag(element_type, attrs, f"{children}{chevron_html}")

    def build_item_class_name(
        self,
        menubar_styles: Any,
        *,
        element_type: str,
        is_disabled: bool,
        level: int,
        is_open: bool = False,
        has_dropdown: bool = False,
        user_class: Any = None,
    ) -> str:
        # Class order matches the React cx() call in MenubarMenuItem, with the user className
        # merged after the defaults (mergeProps ordering).
        return self.join_classes(
            self.get_style_class(menubar_styles, "menubarMenuItem"),
            self.get_style_class(menubar_styles, "menubarMenuItemButton")
            if element_type == "button"
            else None,
            self.get_style_class(menubar_styles, "disabled") if is_disabled else None,
            self.get_style_class(menubar_styles, "subMenu") if level > 0 else None,
            self.get_style_class(menubar_styles, "isOpen") if is_open else None,
            self.get_style_class(menubar_styles, "hasDropdown") if has_dropdown else None,
            self.get_style_class(menubar_styles, "rootMenuItem") if level == 0 else None,
            str(user_class) if user_class else None,
        )

    def build_content_attrs(self, menubar_styles: Any, level: int) -> dict[str, Any]:
        return {
            "className": self.get_style_class(menubar_styles, "menubarMenuItemContent"),
            "data-contentlevel": level,
        }


class UIMenubarRenderer(UIMenubarComponentRendererBase):
    component_name = "menubar"
    supported_props = frozenset(
        {
            "id",
            "className",
            "style",
            "layout",
            "shouldFocusWrap",
            "defaultFocusedKey",
            "defaultExpandedKeys",
            "renderWhenEmpty",
        }
    )
    unsupported_prop_reasons = _MENUBAR_UNSUPPORTED_PROPS
    allow_aria_props = False
    extra_allowed_aria_props = frozenset({"aria-label", "aria-labelledby", "aria-describedby"})
    non_scalar_props = frozenset({"defaultExpandedKeys"})

    def resolve_component_resources(self) -> list[FrontendResource]:
        # Icon.css and Popover.css are included unconditionally: submenu chevrons and flyout
        # popovers are part of normal menubar output, and conditional inclusion would make
        # resource discovery non-deterministic.
        resources = [
            self.resolve_frontend_resource(_MENUBAR_STYLE_PATH),
            self.resolve_frontend_resource(_POPOVER_STYLE_PATH),
            self.resolve_frontend_resource(ICON_STYLE_PATH),
        ]
        runtime_resource = self._resolve_runtime_resource()
        if runtime_resource is not None:
            resources.append(runtime_resource)
        return resources

    def _resolve_runtime_resource(self) -> FrontendResource | None:
        runtime_path = self.resolve_optional_resource_path(
            _RUNTIME_MODULE_PATH,
            resolve_extensions=[".ts", ".tsx", ".js", ".mjs"],
        )
        if runtime_path is None:
            return None
        return FrontendResource.from_path(runtime_path)

    def render_children_for_component(self, context: Context, props: dict[str, Any]) -> str:
        # Children are rendered in render_component so the render state (which render_component
        # needs for empty pruning) wraps them.
        return ""

    def resolve_expanded_keys(self, props: dict[str, Any]) -> frozenset[str]:
        raw = props.get("defaultExpandedKeys")
        if raw is None:
            return frozenset()
        if isinstance(raw, str):
            return frozenset(key.strip() for key in raw.split(",") if key.strip())
        if isinstance(raw, (list, tuple, set, frozenset)):
            return frozenset(str(key) for key in raw)
        warnings.warn(
            "Prop 'defaultExpandedKeys' must be a list of keys or a comma-separated string; "
            "it will be ignored"
        )
        return frozenset()

    def build_render_state(self, props: dict[str, Any], layout: str) -> MenubarRenderState:
        default_focused_key = props.get("defaultFocusedKey")
        return MenubarRenderState(
            layout=layout,  # type: ignore[arg-type] # validated by caller
            orientation="horizontal" if layout == "horizontal" else "vertical",
            should_focus_wrap=props.get("shouldFocusWrap") is not False,
            default_focused_key=str(default_focused_key) if default_focused_key is not None else None,
            expanded_keys=self.resolve_expanded_keys(props),
            frame_stack=[MenubarRenderFrame(level=0)],
        )

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        layout = self.validate_enum_prop(
            props,
            prop_name="layout",
            valid_values=VALID_LAYOUTS,
            default_value="horizontal",
        )
        if not props.get("aria-label") and not props.get("aria-labelledby"):
            warnings.warn(
                "The 'menubar' component should have an 'aria_label' or 'aria_labelledby' prop "
                "for accessibility"
            )

        state = self.build_render_state(props, layout)
        with _push_menubar_state(context, state):
            children_html = self.render_children(context)

        root_frame = state.frame_stack[0]
        if root_frame.item_count == 0 and not props.get("renderWhenEmpty"):
            return ""

        menubar_styles = self.resolve_menubar_styles()
        popover_styles = self.resolve_vanilla_extract_mapping(_POPOVER_STYLE_PATH)

        # Class order matches the React cx() call: base class, user className, then layout classes
        class_name = self.join_classes(
            self.get_style_class(menubar_styles, "menubar"),
            props.get("className"),
            self.get_style_class(menubar_styles, "vertical") if state.orientation == "vertical" else None,
            self.get_style_class(menubar_styles, "inline") if layout == "inline" else None,
            self.get_style_class(menubar_styles, "horizontal") if layout == "horizontal" else None,
        )

        attrs: dict[str, Any] = {
            "data-apui": "menubar",
            "data-layout": layout,
            "data-orientation": state.orientation,
            "role": "menubar",
            "aria-orientation": state.orientation,
            "className": class_name,
            "id": props.get("id"),
            "style": props.get("style"),
            "data-should-focus-wrap": "false" if not state.should_focus_wrap else None,
            "data-default-focused-key": state.default_focused_key,
            # State class names the runtime toggles; it cannot resolve the CSS mapping itself.
            "data-open-class": self.get_style_class(menubar_styles, "isOpen") or None,
            "data-focused-class": self.get_style_class(menubar_styles, "isFocused") or None,
            "data-popover-open-class": self.get_style_class(popover_styles, "isOpen") or None,
            **self.collect_data_aria_attrs(props),
        }

        runtime_resource = self._resolve_runtime_resource()
        script_html = ""
        if runtime_resource is not None:
            script_html = attach_module_script(runtime_resource, attrs)

        return f"{self._render_tag('ul', attrs, children_html)}{script_html}"


class UIMenubarItemRenderer(UIMenubarComponentRendererBase):
    component_name = "menubar_item"
    supported_props = frozenset(
        {
            "id",
            "key",
            "className",
            "style",
            "href",
            "elementType",
            "textValue",
            "isDisabled",
            "isCurrent",
            "target",
            "rel",
            "download",
            "type",
            "form",
            "name",
            "value",
            "formAction",
            "formMethod",
            "formEncType",
            "formNoValidate",
            "formTarget",
            "title",
            "tabIndex",
        }
    )
    unsupported_prop_reasons = {
        "onAction": _CALLBACK_REASON,
        "childItems": _COLLECTION_REASON,
        "hasChildItems": _COLLECTION_REASON,
    }
    prop_aliases = {"disabled": "isDisabled", "current": "isCurrent"}

    #: props only rendered for anchor items
    anchor_only_props = frozenset({"target", "rel", "download"})
    #: props only rendered for button items
    button_only_props = frozenset(
        {
            "type",
            "form",
            "name",
            "value",
            "formAction",
            "formMethod",
            "formEncType",
            "formNoValidate",
            "formTarget",
        }
    )

    def resolve_element_type(self, props: dict[str, Any], is_disabled: bool) -> str:
        element_type = self.validate_optional_enum_prop(
            props, prop_name="elementType", valid_values=VALID_ITEM_ELEMENT_TYPES
        )
        if element_type is None:
            element_type = "a" if props.get("href") and not is_disabled else "div"
        if is_disabled and element_type == "a":
            # Matches React: a disabled anchor renders as a div so it cannot be followed
            element_type = "div"
        return element_type

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        state = self.get_state_or_warn(context)
        effective_state = state or self.make_fallback_state()
        level = effective_state.current_frame.level

        is_disabled = bool(props.get("isDisabled"))
        element_type = self.resolve_element_type(props, is_disabled)
        key = self.resolve_key(props)
        text_value = self.resolve_text_value(props, children_html, content_description="content")
        is_current, aria_current = self.resolve_is_current(props)

        menubar_styles = self.resolve_menubar_styles()

        if "tabIndex" in props:
            tab_index: Any = props["tabIndex"]
        else:
            tab_index = self.claim_tab_index(state, key, is_disabled)

        attrs: dict[str, Any] = {
            "role": "menuitem",
            "className": self.build_item_class_name(
                menubar_styles,
                element_type=element_type,
                is_disabled=is_disabled,
                level=level,
                user_class=props.get("className"),
            ),
            "id": props.get("id"),
            "style": props.get("style"),
            "data-level": level,
            "data-disabled": "true" if is_disabled else None,
            "aria-disabled": "true" if is_disabled else None,
            "aria-label": text_value,
            "tabIndex": tab_index,
            "data-current": "true" if is_current else None,
            "title": props.get("title"),
            **self.collect_data_aria_attrs(props),
        }
        if aria_current is not None:
            attrs["aria-current"] = aria_current

        if element_type == "a":
            attrs["href"] = props.get("href")
        for prop_name in self.anchor_only_props:
            if prop_name in props:
                if element_type == "a":
                    attrs[prop_name] = props[prop_name]
                else:
                    warnings.warn(
                        f"Prop '{prop_name}' is only supported when 'menubar_item' renders an anchor "
                        "and will be ignored"
                    )
        for prop_name in self.button_only_props:
            if prop_name in props:
                if element_type == "button":
                    attrs[prop_name] = props[prop_name]
                else:
                    warnings.warn(
                        f"Prop '{prop_name}' is only supported when 'menubar_item' renders a button "
                        "element and will be ignored"
                    )

        self.track_rendered_child(state, is_current)

        item_html = self.render_menu_item_element(
            element_type=element_type,
            attrs=attrs,
            content_attrs=self.build_content_attrs(menubar_styles, level),
            content_html=self.wrap_plain_text_content(children_html),
        )
        li_attrs: dict[str, Any] = {"role": "none", "data-key": key}
        return self._render_tag("li", li_attrs, item_html)


class UIMenubarSubMenuRenderer(UIMenubarComponentRendererBase):
    component_name = "menubar_submenu"
    supported_props = frozenset(
        {
            "id",
            "key",
            "className",
            "style",
            "title",
            "textValue",
            "href",
            "elementType",
            "isDisabled",
            "isCurrent",
            "hideWhenEmpty",
        }
    )
    unsupported_prop_reasons = {
        "onAction": _CALLBACK_REASON,
        "childItems": _COLLECTION_REASON,
    }
    prop_aliases = {"disabled": "isDisabled", "current": "isCurrent"}
    non_scalar_props = frozenset({"title"})

    def render_children_for_component(self, context: Context, props: dict[str, Any]) -> str:
        # Children are rendered in render_component inside the nested frame
        return ""

    def resolve_trigger_element_type(self, props: dict[str, Any], is_disabled: bool) -> str:
        element_type = self.validate_optional_enum_prop(
            props, prop_name="elementType", valid_values=VALID_ITEM_ELEMENT_TYPES
        )
        if element_type is None:
            element_type = "a" if props.get("href") and not is_disabled else "button"
        if is_disabled and element_type == "a":
            element_type = "div"
        return element_type

    def resolve_chevron_direction(
        self, state: MenubarRenderState, level: int, is_open: bool
    ) -> Literal["up", "down", "right"]:
        # Matches the iconDirection logic in MenubarMenuItem
        effective_orientation = "vertical" if level > 0 else state.orientation
        if (state.layout != "vertical" and effective_orientation == "horizontal") or state.layout == "inline":
            return "up" if is_open else "down"
        return "right"

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        state = self.get_state_or_warn(context)
        ephemeral_state = None
        if state is None:
            # Render children with a fallback state so nested components still work
            ephemeral_state = self.make_fallback_state()
        effective_state = state or ephemeral_state
        assert effective_state is not None
        parent_frame = effective_state.current_frame
        level = parent_frame.level
        child_frame = MenubarRenderFrame(level=level + 1)

        if ephemeral_state is not None:
            with _push_menubar_state(context, ephemeral_state):
                with _push_menubar_frame(ephemeral_state, child_frame):
                    children_html = self.render_children(context)
        else:
            with _push_menubar_frame(effective_state, child_frame):
                children_html = self.render_children(context)

        hide_when_empty = props.get("hideWhenEmpty") is not False
        if child_frame.item_count == 0 and hide_when_empty:
            return ""

        title = props.get("title")
        title_html = render_content(title, context, prop_name="title", origin=self.origin)
        if not title_html.strip():
            warnings.warn("'menubar_submenu' requires a 'title' prop; the submenu will not be rendered")
            return ""

        is_disabled = bool(props.get("isDisabled"))
        element_type = self.resolve_trigger_element_type(props, is_disabled)
        key = self.resolve_key(props)
        text_value = self.resolve_text_value(props, title_html, content_description="'title' content")
        is_current_self, aria_current = self.resolve_is_current(props)
        is_current = is_current_self or child_frame.contains_current
        is_open = key is not None and key in effective_state.expanded_keys and not is_disabled

        menubar_styles = self.resolve_menubar_styles()
        popover_styles = self.resolve_vanilla_extract_mapping(_POPOVER_STYLE_PATH)

        popup_id = f"apui-menu-{key}" if key is not None else self.generate_html_id(context, "apui-menu")

        chevron_direction = self.resolve_chevron_direction(effective_state, level, is_open)
        chevron_svg_path = {
            "up": _CHEVRON_UP_SVG_PATH,
            "down": _CHEVRON_DOWN_SVG_PATH,
            "right": _CHEVRON_RIGHT_SVG_PATH,
        }[chevron_direction]
        chevron_html = self.render_icon(
            chevron_svg_path, "xs", [self.get_style_class(menubar_styles, "dropdownIcon")]
        )

        if "tabIndex" in props:
            tab_index: Any = props["tabIndex"]
        else:
            tab_index = self.claim_tab_index(state, key, is_disabled)

        trigger_attrs: dict[str, Any] = {
            "role": "menuitem",
            "className": self.build_item_class_name(
                menubar_styles,
                element_type=element_type,
                is_disabled=is_disabled,
                level=level,
                is_open=is_open,
                has_dropdown=True,
                user_class=props.get("className"),
            ),
            "id": props.get("id"),
            "style": props.get("style"),
            "data-level": level,
            "data-open": "true" if is_open else "false",
            "data-has-dropdown": "true",
            "data-disabled": "true" if is_disabled else None,
            "aria-disabled": "true" if is_disabled else None,
            "aria-label": text_value,
            "aria-haspopup": "true",
            "aria-expanded": "true" if is_open else "false",
            "aria-controls": popup_id,
            "tabIndex": tab_index,
            "data-current": "true" if is_current else None,
            **self.collect_data_aria_attrs(props),
        }
        if aria_current is not None:
            trigger_attrs["aria-current"] = aria_current
        if element_type == "a":
            trigger_attrs["href"] = props.get("href")
        elif element_type == "button":
            trigger_attrs["type"] = "button"

        trigger_html = self.render_menu_item_element(
            element_type=element_type,
            attrs=trigger_attrs,
            content_attrs=self.build_content_attrs(menubar_styles, level),
            content_html=self.wrap_plain_text_content(title_html),
            chevron_html=chevron_html,
        )

        popup_html = self.render_popup(
            context,
            state=effective_state,
            level=level,
            popup_id=popup_id,
            is_open=is_open,
            children_html=children_html,
            menubar_styles=menubar_styles,
            popover_styles=popover_styles,
        )

        self.track_rendered_child(state, is_current)

        li_attrs: dict[str, Any] = {
            "role": "none",
            "data-key": key,
            "data-apui-menu-submenu": True,
        }
        return self._render_tag("li", li_attrs, f"{trigger_html}{popup_html}")

    def render_popup(
        self,
        context: Context,
        *,
        state: MenubarRenderState,
        level: int,
        popup_id: str,
        is_open: bool,
        children_html: str,
        menubar_styles: Any,
        popover_styles: Any,
    ) -> str:
        menu_style: Any = None
        level_var_reference = self.get_nested_style_class(menubar_styles, "vars", "level")
        level_var = _extract_css_var_name(level_var_reference) if level_var_reference else None
        if level_var:
            menu_style = {level_var: str(level + 1)}

        menu_attrs: dict[str, Any] = {
            "role": "menu",
            "id": popup_id,
            "className": self.join_classes(
                self.get_style_class(menubar_styles, "menubarMenu"),
                self.get_style_class(menubar_styles, "vertical"),
            ),
            "style": menu_style,
        }

        if state.layout == "inline":
            menu_attrs["hidden"] = not is_open
            menu_attrs["data-apui-menu-popup"] = True
            return self._render_tag("ul", menu_attrs, children_html)

        menu_html = self._render_tag("ul", menu_attrs, children_html)
        placement = "bottom" if level == 0 and state.orientation == "horizontal" else "right"
        popover_class = self.join_classes(
            self.get_nested_style_class(popover_styles, "popover", placement),
            self.get_style_class(popover_styles, "isOpen") if is_open else None,
        )
        popover_attrs: dict[str, Any] = {
            "className": popover_class,
            "role": "presentation",
            "hidden": not is_open,
            "data-apui-menu-popover": True,
            "data-placement": placement,
        }
        inner_class = conditional_escape(self.get_style_class(popover_styles, "inner"))
        return self._render_tag("div", popover_attrs, f'<div class="{inner_class}">{menu_html}</div>')


class UIMenubarSectionRenderer(UIMenubarComponentRendererBase):
    component_name = "menubar_section"
    supported_props = frozenset(
        {
            "id",
            "key",
            "className",
            "style",
            "separatorClassName",
            "title",
            "hideWhenEmpty",
        }
    )
    unsupported_prop_reasons = {"items": _COLLECTION_REASON}
    non_scalar_props = frozenset({"title"})

    def render_children_for_component(self, context: Context, props: dict[str, Any]) -> str:
        # Children are rendered in render_component inside the nested frame
        return ""

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        state = self.get_state_or_warn(context)
        ephemeral_state = None
        if state is None:
            ephemeral_state = self.make_fallback_state()
        effective_state = state or ephemeral_state
        assert effective_state is not None
        parent_frame = effective_state.current_frame
        # Sections group items within the same menu so the level does not increase
        child_frame = MenubarRenderFrame(level=parent_frame.level)
        is_first = parent_frame.item_count == 0

        if ephemeral_state is not None:
            with _push_menubar_state(context, ephemeral_state):
                with _push_menubar_frame(ephemeral_state, child_frame):
                    children_html = self.render_children(context)
        else:
            with _push_menubar_frame(effective_state, child_frame):
                children_html = self.render_children(context)

        hide_when_empty = props.get("hideWhenEmpty") is not False
        if child_frame.item_count == 0 and hide_when_empty:
            return ""

        title = props.get("title")
        title_html = render_content(title, context, prop_name="title", origin=self.origin)

        menubar_styles = self.resolve_menubar_styles()

        heading_html = ""
        heading_id: str | None = None
        if title_html.strip():
            heading_id = self.generate_html_id(context, "apui-menubar")
            if "<" not in title_html.strip():
                heading_text_class = conditional_escape(
                    self.get_style_class(menubar_styles, "sectionHeadingText")
                )
                title_html = mark_safe(f'<span class="{heading_text_class}">{title_html.strip()}</span>')
            heading_attrs: dict[str, Any] = {
                "className": self.get_style_class(menubar_styles, "sectionHeading"),
                "id": heading_id,
                "role": "presentation",
            }
            heading_html = self._render_tag("div", heading_attrs, title_html)

        separator_html = ""
        if not is_first:
            # Root level horizontal menus use a vertical separator, matching useSeparator usage
            is_vertical_separator = effective_state.layout == "horizontal" and parent_frame.level == 0
            separator_attrs: dict[str, Any] = {
                "role": "separator",
                "aria-orientation": "vertical" if is_vertical_separator else None,
                "className": self.join_classes(
                    self.get_style_class(menubar_styles, "separator"),
                    props.get("separatorClassName"),
                ),
            }
            separator_html = self._render_tag("li", separator_attrs, "")

        group_attrs: dict[str, Any] = {
            "role": "group",
            "aria-labelledby": heading_id,
            "aria-label": props.get("aria-label") if heading_id is None else None,
        }
        group_html = self._render_tag("ul", group_attrs, children_html)

        section_attrs: dict[str, Any] = {
            "role": "presentation",
            "className": self.join_classes(
                self.get_style_class(menubar_styles, "section"),
                props.get("className"),
            ),
            "id": props.get("id"),
            "style": props.get("style"),
            "data-key": self.resolve_key(props),
            "data-current": "true" if child_frame.contains_current else None,
            **self.collect_data_aria_attrs({k: v for k, v in props.items() if k != "aria-label"}),
        }
        section_html = self._render_tag("li", section_attrs, f"{heading_html}{group_html}")

        self.track_rendered_child(state, child_frame.contains_current)

        return mark_safe(f"{separator_html}{section_html}")
