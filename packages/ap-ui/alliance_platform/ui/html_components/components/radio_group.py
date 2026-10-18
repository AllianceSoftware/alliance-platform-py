"""Static HTML renderers for ``RadioGroup`` and ``Radio`` from ``@alliancesoftware/ui``.

See :mod:`.choice` for the markup the radio group shares with the checkbox group.
"""

from __future__ import annotations

from typing import Any

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from alliance_platform.frontend.templatetags.react import OmitComponentFromRendering
from django.template import Context
from django.utils.html import conditional_escape

from ..base import BaseHtmlUIComponentRenderer
from ..render_context import find_render_payload
from .choice import CHECKBOX_STYLE_PATH
from .choice import RADIO_GROUP_STYLE_PATH
from .choice import ChoiceGroupRenderState
from .choice import UIChoiceGroupRendererBase
from .choice import group_props_supported
from .choice import group_react_only_reasons
from .choice import joined_ids
from .choice import render_box
from .choice import render_choice_label


class RadioGroupRenderState(ChoiceGroupRenderState):
    """The payload a ``radio_group`` pushes for the radios inside it."""


class UIRadioGroupRenderer(UIChoiceGroupRendererBase):
    """Mirrors ``RadioGroup.tsx``: the label, help text and error message of ``LabeledInput``
    around a ``role="radiogroup"`` element holding the radios.

    The radios share the group's name, generated when none is given, so the browser checks one at a
    time and moves between them with the arrow keys.
    """

    name = "radio_group"
    react_tag = 'component "@alliancesoftware/ui" "RadioGroup"'
    render_state_class = RadioGroupRenderState
    group_style_path = RADIO_GROUP_STYLE_PATH
    supported_props = group_props_supported()
    # value=None checks no radio, whatever the defaultValue, as null does in React
    none_meaningful_props = frozenset({"value"})
    unsupported_prop_reasons = group_react_only_reasons("static radio groups")
    prop_filter_context = "static radio groups"
    event_handler_prop_reason = "event handlers are not supported by static radio groups"
    prop_docs = {
        "id": (
            "The group's id, which also names the label ``<id>_label``, the help text ``<id>_helptext`` "
            "and the error message ``<id>_error``."
        ),
        "name": "Generated when absent, as React generates one, so the radios form one group.",
        "defaultValue": "Same as ``value``: the browser changes the checked radio from there.",
        "validationState": '``"invalid"`` sets ``is_invalid``, as react-aria reads it.',
    }

    def resolve_name(self, context: Context, props: dict[str, Any]) -> str | None:
        # Allocated after the label, help text and error message ids, as react-aria does
        return super().resolve_name(context, props) or self.generate_html_id(context)

    def resolve_selected_values(self, props: dict[str, Any]) -> frozenset[str]:
        value = props["value"] if "value" in props else props.get("defaultValue")
        return frozenset() if value is None else frozenset({str(value)})

    def get_group_attrs(self, props: dict[str, Any], state: ChoiceGroupRenderState) -> dict[str, Any]:
        styles = self.resolve_vanilla_extract_mapping(self.group_style_path)
        return {
            # The state react-aria's useRadioGroup gives the group
            "role": "radiogroup",
            "aria-invalid": "true" if state.is_invalid else None,
            "aria-readonly": "true" if state.is_read_only else None,
            "aria-required": "true" if state.labeled_input.is_required else None,
            "aria-disabled": "true" if state.is_disabled else None,
            "aria-orientation": state.orientation,
            **super().get_group_attrs(props, state),
            "className": self.get_style_class(styles, "radioGroup"),
            "data-apui": self.apui_name,
            "data-orientation": state.orientation,
            "data-invalid": "true" if state.is_invalid else None,
            "data-disabled": "true" if state.is_disabled else None,
        }


class UIRadioRenderer(BaseHtmlUIComponentRenderer):
    """Mirrors ``Radio`` in ``RadioGroup.tsx``: the native radio and the box the stylesheet draws over
    it, in a ``<label>`` holding the children as the label. It takes its name, size, checked state
    and the group's disabled, read only and invalid states from its ``radio_group``."""

    name = "radio"
    react_tag = 'component "@alliancesoftware/ui" "Radio"'
    supported_props = frozenset({"children", "value", "isDisabled", "id", "autoFocus"})
    deprecated_prop_aliases = {"disabled": "isDisabled"}
    allow_data_props = True
    allow_aria_props = True
    prop_filter_context = "static radios"
    event_handler_prop_reason = "event handlers are not supported by static radios"
    requires_radio_group = True
    prop_docs = {
        "id": "The input's id, such as the id Django gives the option.",
    }

    def resolve_component_resources(self) -> list[FrontendResource]:
        return [
            self.resolve_frontend_resource(RADIO_GROUP_STYLE_PATH),
            self.resolve_frontend_resource(CHECKBOX_STYLE_PATH),
        ]

    def resolve_props(self, context: Context) -> dict[str, Any]:
        if find_render_payload(context, RadioGroupRenderState) is None:
            self.report(
                "'radio' was rendered outside of a '{% ui \"radio_group\" %}' component; rendering nothing",
                kind="contract",
            )
            raise OmitComponentFromRendering()
        return super().resolve_props(context)

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        group = find_render_payload(context, RadioGroupRenderState)
        assert group is not None
        styles = self.resolve_vanilla_extract_mapping(RADIO_GROUP_STYLE_PATH)
        value = props.get("value")
        if value is None:
            self.report("'radio' needs a 'value', the value its group submits for it", kind="contract")
        is_disabled = bool(props.get("isDisabled")) or group.is_disabled

        input_attrs: dict[str, Any] = {
            "type": "radio",
            "name": group.name,
            "value": value,
            "checked": value is not None and str(value) in group.selected_values,
            "disabled": is_disabled,
            "id": props.get("id") or None,
            "autoFocus": bool(props.get("autoFocus")),
            "aria-describedby": joined_ids(props.get("aria-describedby"), *group.item_described_by),
        }
        for key, attr_value in props.items():
            if key.startswith(("data-", "aria-")) and key not in input_attrs:
                input_attrs[key] = attr_value
        input_attrs["className"] = self.get_style_class(styles, "input")

        box_html = render_box(
            self,
            self.get_style_class(styles, "radio"),
            self.get_style_class(styles, "icon"),
            f'<circle cx="8" cy="8" r="3" '
            f'class="{conditional_escape(self.get_style_class(styles, "radioCheck"))}"></circle>',
        )
        # Checkbox.css styles the box and RadioGroup.css the dot from the input and these attributes
        root_attrs: dict[str, Any] = {
            "className": self.get_style_class(styles, "wrapper"),
            "data-apui": self.apui_name,
            "data-size": group.labeled_input.input_size,
            "data-invalid": "true" if group.is_invalid else None,
            "data-disabled": "true" if is_disabled else None,
            "data-readonly": "true" if group.is_read_only else None,
        }
        return self.render_tag(
            "label",
            root_attrs,
            f"<input{self.build_attrs_string(input_attrs)}/>{box_html}"
            f"{render_choice_label(self.get_style_class(styles, 'label'), children_html)}",
        )
