"""Static HTML renderers for ``Checkbox`` and ``CheckboxGroup`` from ``@alliancesoftware/ui``.

See :mod:`.choice` for the markup the checkbox and its group share with the radio group.
"""

from __future__ import annotations

from typing import Any

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from django.template import Context

from ..base import BaseHtmlUIComponentRenderer
from ..base import enum_prop_rule
from ..content import has_renderable_content
from ..content import is_rich_content_value
from ..content import render_content
from ..render_context import find_render_payload
from ..render_context import generate_html_id
from .choice import CHECKBOX_GROUP_STYLE_PATH
from .choice import CHECKBOX_STYLE_PATH
from .choice import GROUP_NOT_RENDERED_PROP_DOCS
from .choice import ChoiceGroupRenderState
from .choice import UIChoiceGroupRendererBase
from .choice import group_props_supported
from .choice import group_react_only_reasons
from .choice import joined_ids
from .choice import render_box
from .choice import render_choice_label
from .choice import render_mark_path
from .input import _FORM_SECTION_STYLE_PATH
from .input import _LABELED_INPUT_STYLE_PATH
from .input import VALID_LABEL_POSITIONS
from .input import VALID_VALIDATION_STATES

VALID_CHECKBOX_SIZES = ("sm", "md")

_CHECK_MARK_PATH = "M12 5L6.5 10.5L4 8"
_INDETERMINATE_MARK_PATH = "M4.5 8H11.5"

_LABEL_PROP_DOC = (
    "Accepted, as ``{% form_input %}`` passes it, and not rendered: a checkbox's label is its children, "
    "as in React."
)


class CheckboxGroupRenderState(ChoiceGroupRenderState):
    """The payload a ``checkbox_group`` pushes for the checkboxes inside it."""


class UICheckboxRenderer(BaseHtmlUIComponentRenderer):
    """Mirrors ``Checkbox.tsx``: the native checkbox and the box the stylesheet draws over it, in a
    ``<label>`` holding the children as the label.

    On its own the checkbox renders in the row ``FormLayout`` gives it: a ``<div>`` marked with the
    label position and the invalid state, holding an empty label cell in the side layout, and the
    description after the checkbox, or the error message in its place while it is invalid, as
    ``LabeledInput`` renders them. A given ``id`` names them ``<id>_helptext`` and ``<id>_error``, as
    Django names a form field's. Inside a ``checkbox_group`` it takes its name, checked state and the
    group's disabled, read only and invalid states from the group, as React's
    ``useCheckboxGroupItem`` does, and renders no row or help text: the group renders its own.
    """

    name = "checkbox"
    react_tag = 'component "@alliancesoftware/ui" "Checkbox"'
    supported_props = frozenset(
        {
            "children",
            "className",
            "name",
            "value",
            "isSelected",
            "defaultSelected",
            "isIndeterminate",
            "isDisabled",
            "isReadOnly",
            "isRequired",
            "isInvalid",
            "validationState",
            "size",
            "labelPosition",
            "id",
            "form",
            "autoFocus",
            "excludeFromTabOrder",
            "label",
            "description",
            "errorMessage",
        }
    )
    # Django's CheckboxInput sets the native checked attribute
    prop_aliases = {"checked": "defaultSelected"}
    deprecated_prop_aliases = {"disabled": "isDisabled"}
    prop_rules = {
        "size": enum_prop_rule(VALID_CHECKBOX_SIZES, invalid_fallback="sm"),
        "labelPosition": enum_prop_rule(VALID_LABEL_POSITIONS, invalid_fallback="top"),
        "validationState": enum_prop_rule(VALID_VALIDATION_STATES),
    }
    unsupported_prop_reasons = {
        key: "React-only props are not supported by static checkboxes"
        for key in ("inputRef", "labelRef", "ref", "parentIsHovered", "validationBehavior", "validate")
    }
    # As the inputs', the help text and error message render rich content, such as the help text and
    # safe error messages {% form_input %} passes
    rich_content_props = frozenset({"description", "errorMessage"})
    allow_data_props = True
    allow_aria_props = True
    prop_filter_context = "static checkboxes"
    event_handler_prop_reason = "event handlers are not supported by static checkboxes"
    prop_docs = {
        "defaultSelected": (
            "Renders the input checked, as ``is_selected`` does; the browser toggles it from there. "
            "``checked`` is the attribute Django's ``CheckboxInput`` sets."
        ),
        "isSelected": "Renders the input checked; the browser toggles it from there.",
        "isIndeterminate": (
            "Marks the root with ``data-indeterminate``, which shows the dash. The input's "
            "``indeterminate`` state needs a script, so assistive technology announces the checkbox as "
            "checked or not checked until one sets it."
        ),
        "labelPosition": (
            "The form layout the checkbox renders in on its own: ``side`` renders an empty label cell "
            "before it, as React does in a side ``FormSection``."
        ),
        "validationState": '``"invalid"`` sets ``is_invalid``, as react-aria reads it.',
        "label": _LABEL_PROP_DOC,
    }

    def resolve_component_resources(self) -> list[FrontendResource]:
        return [
            self.resolve_frontend_resource(CHECKBOX_STYLE_PATH),
            self.resolve_frontend_resource(_FORM_SECTION_STYLE_PATH),
            self.resolve_frontend_resource(_LABELED_INPUT_STYLE_PATH),
        ]

    def allow_non_scalar_prop(self, key: str, value: Any) -> bool:
        return key in self.rich_content_props and is_rich_content_value(value)

    def report_group_misuse(self, props: dict[str, Any]) -> None:
        # The warnings React's Checkbox gives inside a CheckboxGroup
        invalid_keys = [key for key in ("isSelected", "defaultSelected") if props.get(key) is not None]
        if invalid_keys:
            self.report(
                "When <Checkbox> is used within a <CheckboxGroup>, the following keys must be applied "
                f"at the <CheckboxGroup> level rather than <Checkbox>: {', '.join(invalid_keys)}",
                kind="contract",
            )
        if props.get("value") is None:
            self.report(
                "When <Checkbox> is used within a <CheckboxGroup> it must have a `value` prop.",
                kind="contract",
            )

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        styles = self.resolve_vanilla_extract_mapping(CHECKBOX_STYLE_PATH)
        group = find_render_payload(context, CheckboxGroupRenderState)
        value = props.get("value")
        is_required = bool(props.get("isRequired"))
        is_disabled = bool(props.get("isDisabled"))
        is_read_only = bool(props.get("isReadOnly"))
        is_invalid = bool(props.get("isInvalid")) or props.get("validationState") == "invalid"
        help_text_html = ""
        if group is None:
            name = props.get("name")
            selected = props["isSelected"] if "isSelected" in props else props.get("defaultSelected")
            is_checked = bool(selected)
            help_text_html, help_text_id = self.render_help_text(context, props, is_invalid)
            # The help text that renders, before any ids the caller gives, each once: the
            # aria-describedby Django 5.0+ gives a form widget names the same ids
            described_by = joined_ids(help_text_id, props.get("aria-describedby"))
        else:
            self.report_group_misuse(props)
            name = props.get("name") or group.name
            is_checked = value is not None and str(value) in group.selected_values
            is_disabled = is_disabled or group.is_disabled
            is_read_only = is_read_only or group.is_read_only
            is_invalid = is_invalid or group.is_invalid
            described_by = joined_ids(props.get("aria-describedby"), *group.item_described_by)
        is_indeterminate = bool(props.get("isIndeterminate"))

        input_attrs: dict[str, Any] = {
            "type": "checkbox",
            "name": name,
            "value": value,
            "checked": is_checked,
            "disabled": is_disabled,
            "id": props.get("id") or None,
            "form": props.get("form"),
            "autoFocus": bool(props.get("autoFocus")),
            "tabIndex": "-1" if props.get("excludeFromTabOrder") else None,
            "aria-invalid": "true" if is_invalid else None,
            "aria-required": "true" if is_required else None,
            "aria-readonly": "true" if is_read_only else None,
            "aria-describedby": described_by,
        }
        for key, attr_value in props.items():
            if key.startswith(("data-", "aria-")) and key not in input_attrs:
                input_attrs[key] = attr_value
        input_attrs["className"] = self.get_style_class(styles, "input")

        border_class = self.get_style_class(styles, "border")
        marks = render_mark_path(
            _CHECK_MARK_PATH, self.join_classes(border_class, self.get_style_class(styles, "checkMark"))
        ) + render_mark_path(
            _INDETERMINATE_MARK_PATH,
            self.join_classes(border_class, self.get_style_class(styles, "indeterminateMark")),
        )
        box_html = render_box(
            self.get_style_class(styles, "checkbox"), self.get_style_class(styles, "icon"), marks
        )
        # The stylesheet styles the box, its marks and the label from the input and these attributes
        root_attrs: dict[str, Any] = {
            "className": self.join_classes(self.get_style_class(styles, "wrapper"), props.get("className")),
            "data-apui": self.apui_name,
            "data-size": str(props.get("size", "sm")),
            "data-invalid": "true" if is_invalid else None,
            "data-disabled": "true" if is_disabled else None,
            "data-required": "true" if is_required else None,
            "data-readonly": "true" if is_read_only else None,
            "data-indeterminate": "true" if is_indeterminate else None,
        }
        checkbox_html = self.render_tag(
            "label",
            root_attrs,
            f"<input{self.build_attrs_string(input_attrs)}/>{box_html}"
            f"{render_choice_label(self.get_style_class(styles, 'label'), children_html)}",
        )
        if group is not None:
            return checkbox_html
        return self.render_layout_row(props, f"{checkbox_html}{help_text_html}", is_invalid)

    def render_help_text(
        self, context: Context, props: dict[str, Any], is_invalid: bool
    ) -> tuple[str, str | None]:
        """Render the error message while the checkbox is invalid, or else the description, as
        ``LabeledInput`` renders them, and return it with its id; ``("", None)`` when neither renders."""
        error_message = props.get("errorMessage")
        if is_invalid and has_renderable_content(error_message):
            prop_name, content, suffix = "errorMessage", error_message, "error"
        elif has_renderable_content(props.get("description")):
            prop_name, content, suffix = "description", props["description"], "helptext"
        else:
            return "", None
        # An empty id, as a template variable for a form without auto ids gives, is no id
        given_id = props.get("id") or None
        help_text_id = (
            f"{given_id}_{suffix}"
            if given_id is not None
            else generate_html_id(context, f"apui-{self.apui_name}")
        )
        labeled_input_styles = self.resolve_vanilla_extract_mapping(_LABELED_INPUT_STYLE_PATH)
        html = self.render_tag(
            "div",
            {"className": self.get_style_class(labeled_input_styles, "helpText"), "id": help_text_id},
            render_content(content, context, prop_name=prop_name, origin=self.origin, component=self.name),
        )
        return html, help_text_id

    def render_layout_row(self, props: dict[str, Any], row_content_html: str, is_invalid: bool) -> str:
        """Render the row ``FormLayout.renderLabeledInput`` gives a checkbox with no label of its own.

        The row carries ``data-invalid`` while the checkbox is invalid, which colours its help text as a
        ``LabeledInput`` root's does.
        """
        row_attrs: dict[str, Any] = {"data-invalid": "true" if is_invalid else None}
        if props.get("labelPosition", "top") != "side":
            return self.render_tag("div", {"data-label-position": "top", **row_attrs}, row_content_html)
        form_section_styles = self.resolve_vanilla_extract_mapping(_FORM_SECTION_STYLE_PATH)
        placeholder_html = self.render_tag(
            "div", {"className": self.get_style_class(form_section_styles, "sideLabelPlaceholder")}
        )
        input_cell_html = self.render_tag(
            "div",
            {"className": self.get_style_class(form_section_styles, "inputHelpSideWrapper")},
            row_content_html,
        )
        return self.render_tag(
            "div", {"data-label-position": "side", **row_attrs}, f"{placeholder_html}{input_cell_html}"
        )


class UICheckboxGroupRenderer(UIChoiceGroupRendererBase):
    """Mirrors ``CheckboxGroup.tsx``: the label, help text and error message of ``LabeledInput``
    around a ``role="group"`` element holding the checkboxes."""

    name = "checkbox_group"
    react_tag = 'component "@alliancesoftware/ui" "CheckboxGroup"'
    render_state_class = CheckboxGroupRenderState
    group_style_path = CHECKBOX_GROUP_STYLE_PATH
    supported_props = group_props_supported("hasInvalidChildren")
    non_scalar_props = frozenset({"value", "defaultValue"})
    unsupported_prop_reasons = group_react_only_reasons("static checkbox groups")
    prop_filter_context = "static checkbox groups"
    event_handler_prop_reason = "event handlers are not supported by static checkbox groups"
    prop_docs = {
        "id": (
            "The group's id, which also names the label ``<id>_label``, the help text ``<id>_helptext`` "
            "and the error message ``<id>_error``."
        ),
        "value": (
            "The values of the checked checkboxes. A string checks that one value; React takes a list only."
        ),
        "defaultValue": "Same as ``value``: the browser toggles the checkboxes from there.",
        "validationState": '``"invalid"`` sets ``is_invalid``, as react-aria reads it.',
        **GROUP_NOT_RENDERED_PROP_DOCS,
    }

    def allow_non_scalar_prop(self, key: str, value: Any) -> bool:
        return key in self.non_scalar_props or super().allow_non_scalar_prop(key, value)

    def labeled_input_props(self, props: dict[str, Any]) -> dict[str, Any]:
        # hasInvalidChildren shows the error message, while the group and its checkboxes stay valid
        if props.get("hasInvalidChildren"):
            return {**props, "isInvalid": True}
        return props

    def get_group_attrs(self, props: dict[str, Any], state: ChoiceGroupRenderState) -> dict[str, Any]:
        styles = self.resolve_vanilla_extract_mapping(self.group_style_path)
        return {
            "role": "group",
            **super().get_group_attrs(props, state),
            "aria-disabled": "true" if state.is_disabled else None,
            "className": self.get_style_class(styles, "groupBox"),
            "data-apui": self.apui_name,
            "data-orientation": state.orientation,
            "data-invalid": "true" if state.is_invalid else None,
        }
