"""Shared rendering for the static checkbox and radio groups and the controls in them.

The groups mirror ``CheckboxGroup.tsx`` and ``RadioGroup.tsx`` from ``@alliancesoftware/ui``: a
``LabeledInput`` whose label is a ``<span>`` that labels the group element through
``aria-labelledby``, the group element holding the controls, and the help text or error message
after it. A group renders its children inside a render frame whose payload carries what react-aria's
group state gives each checkbox or radio: the name, the checked values, the disabled, read only and
invalid states and the ids of the help text and error message.

The checkbox and radio controls render the real input inside the root ``<label>``, followed by the
box. The stylesheets show the state of the box, its marks and its label from that input
(``:has(input:checked)``, ``:disabled``, ``:focus-visible``) and from the root's data attributes, so
the markup needs no script: the browser toggles the input and the styles follow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import ClassVar

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from django.template import Context
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from ..base import BaseHtmlUIComponentRenderer
from ..base import enum_prop_rule
from ..render_context import RenderFrame
from ..render_context import get_current_component_frame
from .input import _FORM_SECTION_STYLE_PATH
from .input import _LABEL_STYLE_PATH
from .input import _LABELED_INPUT_PROP_RULES
from .input import _LABELED_INPUT_STYLE_PATH
from .input import LabeledInputState
from .input import UILabeledInputRendererMixin

VALID_ORIENTATIONS = ("vertical", "horizontal")

CHECKBOX_STYLE_PATH = "@alliancesoftware/ui/components/checkbox/Checkbox.css.ts"
CHECKBOX_GROUP_STYLE_PATH = "@alliancesoftware/ui/components/checkbox/CheckboxGroup.css.ts"
RADIO_GROUP_STYLE_PATH = "@alliancesoftware/ui/components/radio-group/RadioGroup.css.ts"

_MARK_STROKE_ATTRS = 'stroke-width="1.6666" stroke-linecap="round" stroke-linejoin="round"'

# Props of the React groups with no static equivalent: the props of the elements LabeledInput
# renders, refs and react-aria's validation
_GROUP_REACT_ONLY_PROPS = frozenset(
    {
        "labelProps",
        "descriptionProps",
        "errorMessageProps",
        "elementType",
        "ref",
        "labelRef",
        "validationBehavior",
        "validate",
    }
)


def render_box(box_class: str, icon_class: str, svg_children: str) -> str:
    """Render the box a checkbox or radio draws in place of the native input, hidden from AT."""
    return (
        f'<span class="{conditional_escape(box_class)}" aria-hidden="true">'
        f'<svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" '
        f'class="{conditional_escape(icon_class)}">{svg_children}</svg></span>'
    )


def render_mark_path(path: str, class_name: str) -> str:
    """Render one of the checkbox marks, the stroked check or indeterminate dash."""
    return f'<path d="{path}" {_MARK_STROKE_ATTRS} class="{conditional_escape(class_name)}"></path>'


def render_choice_label(class_name: str, children_html: str) -> str:
    """Render the label content beside the box, or nothing when there is none, as React does."""
    content = children_html.strip()
    if not content:
        return ""
    return mark_safe(f'<span class="{conditional_escape(class_name)}">{content}</span>')


def joined_ids(*parts: Any) -> str | None:
    """Join space separated id lists, each id once, or ``None`` when there are none."""
    ids = dict.fromkeys(token for part in parts if part for token in str(part).split())
    return " ".join(ids) or None


@dataclass
class ChoiceGroupRenderState:
    """What a checkbox or radio group passes the controls rendered inside it."""

    labeled_input: LabeledInputState
    name: str | None
    #: The checked values, compared as strings
    selected_values: frozenset[str]
    is_disabled: bool
    is_read_only: bool
    #: Whether the group is invalid, which makes its controls invalid. A checkbox group's
    #: ``hasInvalidChildren`` shows the error message without it.
    is_invalid: bool
    orientation: str
    #: The ids each control adds to its ``aria-describedby``: the error message while the group is
    #: invalid, then the help text, as react-aria lists them
    item_described_by: tuple[str, ...]


def selected_value_set(value: Any) -> frozenset[str]:
    """The checked values of a group's ``value``: a list of values, or one value."""
    if value is None:
        return frozenset()
    if isinstance(value, (list, tuple, set, frozenset)):
        return frozenset(str(item) for item in value if item is not None)
    return frozenset({str(value)})


class UIChoiceGroupRendererBase(UILabeledInputRendererMixin, BaseHtmlUIComponentRenderer):
    """Shared rendering for ``checkbox_group`` and ``radio_group``.

    The ``id`` prop is the group element's id, as react-aria gives it to the group, and names the
    label ``<id>_label``, the help text ``<id>_helptext`` and the error message ``<id>_error``.
    """

    # The group's id is only ever the given one; the label gets an id of its own
    generate_input_id = False
    label_element = "span"
    root_marks_disabled = True
    allow_data_props = True
    allow_aria_props = True
    deprecated_prop_aliases = {"disabled": "isDisabled"}
    prop_rules = {
        **_LABELED_INPUT_PROP_RULES,
        "orientation": enum_prop_rule(VALID_ORIENTATIONS, invalid_fallback="vertical"),
    }
    #: The payload the group pushes for its controls
    render_state_class: ClassVar[type[ChoiceGroupRenderState]] = ChoiceGroupRenderState
    #: The stylesheet of the group element
    group_style_path: ClassVar[str]

    def resolve_component_resources(self) -> list[FrontendResource]:
        return [
            self.resolve_frontend_resource(_LABELED_INPUT_STYLE_PATH),
            self.resolve_frontend_resource(_LABEL_STYLE_PATH),
            self.resolve_frontend_resource(_FORM_SECTION_STYLE_PATH),
            self.resolve_frontend_resource(self.group_style_path),
        ]

    def labeled_input_props(self, props: dict[str, Any]) -> dict[str, Any]:
        """The props the group's ``LabeledInput`` renders from."""
        return props

    def is_group_invalid(self, props: dict[str, Any]) -> bool:
        return bool(props.get("isInvalid")) or props.get("validationState") == "invalid"

    def resolve_name(self, context: Context, props: dict[str, Any]) -> str | None:
        name = props.get("name")
        return str(name) if name not in (None, "") else None

    def resolve_selected_values(self, props: dict[str, Any]) -> frozenset[str]:
        value = props["value"] if "value" in props else props.get("defaultValue")
        return selected_value_set(value)

    def build_render_frame(self, context: Context, props: dict[str, Any]) -> RenderFrame:
        # The label, help text and error message ids are allocated before the children render, as
        # each control references them
        labeled_input = self.resolve_labeled_input_state(context, self.labeled_input_props(props))
        is_invalid = self.is_group_invalid(props)
        item_described_by: list[str] = []
        if is_invalid and labeled_input.error_id:
            item_described_by.append(labeled_input.error_id)
        if labeled_input.description_id:
            item_described_by.append(labeled_input.description_id)
        state = self.render_state_class(
            labeled_input=labeled_input,
            name=self.resolve_name(context, props),
            selected_values=self.resolve_selected_values(props),
            is_disabled=labeled_input.is_disabled,
            is_read_only=labeled_input.is_readonly,
            is_invalid=is_invalid,
            orientation=str(props.get("orientation", "vertical")),
            item_described_by=tuple(item_described_by),
        )
        return RenderFrame(component=self.name, payload=state)

    def get_group_state(self, context: Context) -> ChoiceGroupRenderState:
        frame = get_current_component_frame(context)
        assert frame is not None and isinstance(frame.payload, self.render_state_class)
        return frame.payload

    def get_group_attrs(self, props: dict[str, Any], state: ChoiceGroupRenderState) -> dict[str, Any]:
        """The attributes of the group element; renderers add their role and state attributes."""
        labeled_input = state.labeled_input
        attrs: dict[str, Any] = {
            "id": labeled_input.input_id,
            # The group is labelled by its label, then by any labels the caller gives, as react-aria
            # orders them
            "aria-labelledby": joined_ids(labeled_input.label_id, props.get("aria-labelledby")),
            "aria-describedby": labeled_input.described_by,
        }
        for key, value in props.items():
            if key.startswith(("data-", "aria-")) and key not in attrs:
                attrs[key] = value
        return attrs

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        state = self.get_group_state(context)
        group_html = self.render_tag("div", self.get_group_attrs(props, state), children_html)
        return mark_safe(self.render_labeled_input(context, props, state.labeled_input, group_html))


def group_props_supported(*extra: str) -> frozenset[str]:
    """The props both groups take, with ``extra``."""
    return frozenset(
        {
            "label",
            "labelPosition",
            "labelAlign",
            "inputSize",
            "description",
            "errorMessage",
            "validationState",
            "isInvalid",
            "isDisabled",
            "isReadOnly",
            "isRequired",
            "orientation",
            "name",
            "value",
            "defaultValue",
            "id",
            "className",
            "style",
            "children",
            *extra,
        }
    )


def group_react_only_reasons(context_name: str) -> dict[str, str]:
    return {key: f"React-only props are not supported by {context_name}" for key in _GROUP_REACT_ONLY_PROPS}
