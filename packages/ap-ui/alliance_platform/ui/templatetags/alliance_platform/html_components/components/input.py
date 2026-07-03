from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING
from typing import Any
import warnings

from django.template import Context
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource

from ..base import BaseHtmlUIComponentRenderer

if TYPE_CHECKING:
    # The mixin is only ever combined with BaseHtmlUIComponentRenderer; declaring it as the type
    # checking base makes the renderer helper methods available to type checkers.
    _LabeledInputMixinBase = BaseHtmlUIComponentRenderer
else:
    _LabeledInputMixinBase = object

VALID_LABEL_POSITIONS = ("top", "side")
VALID_LABEL_ALIGNS = ("start", "end")
VALID_INPUT_SIZES = ("sm", "md")
VALID_VALIDATION_STATES = ("valid", "invalid")

_TEXT_INPUT_BASE_STYLE_PATH = "@alliancesoftware/ui/components/text-input/TextInputBase.css.ts"
_LABELED_INPUT_STYLE_PATH = "@alliancesoftware/ui/components/form/LabeledInput.css.ts"
_LABEL_STYLE_PATH = "@alliancesoftware/ui/components/form/Label.css.ts"
_FORM_SECTION_STYLE_PATH = "@alliancesoftware/ui/components/form/FormSection.css.ts"
_FOCUS_RING_STYLE_PATH = "@alliancesoftware/ui/styles/base/focusRing.css.ts"
_ICON_STYLE_PATH = "@alliancesoftware/icons/Icon.css.ts"
_NUMBER_INPUT_STYLE_PATH = "@alliancesoftware/ui/components/number-input/NumberInput.css.ts"

# Key used in ``context.render_context`` to keep generated ids unique within a template render.
_HTML_ID_COUNTER_KEY = "alliance_platform_ui_html_id_counter"

# Static SVG markup matching the icons rendered by the React components
# (see @alliancesoftware/icons/outlined/*.tsx). Width/height are set inline by the Icon
# component so icons have a size before stylesheets load.
_SVG_ATTRS = 'width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" focusable="false"'
_SVG_PATH_ATTRS = 'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
_ALERT_CIRCLE_SVG_PATH = (
    "M12 8V12M12 16H12.01M22 12C22 17.5228 17.5228 22 12 22C6.47715 22 2 17.5228 2 12C2 "
    "6.47715 6.47715 2 12 2C17.5228 2 22 6.47715 22 12Z"
)
_CHECK_SVG_PATH = "M20 6L9 17L4 12"
_CHEVRON_UP_SVG_PATH = "M18 15L12 9L6 15"
_CHEVRON_DOWN_SVG_PATH = "M6 9L12 15L18 9"

# Props that only make sense with the React runtime (render props, react-aria plumbing). These are
# warned about and ignored rather than rendered as attributes.
_REACT_ONLY_PROPS = frozenset(
    {
        "renderInput",
        "renderAddonAfter",
        "inputProps",
        "labelProps",
        "descriptionProps",
        "errorMessageProps",
        "containerProps",
        "inputRef",
        "containerRef",
        "labelRef",
        "validationBehavior",
        "validate",
    }
)

# Matches event handler props in any of the forms they can reach us in after prop normalization
# (onClick, onclick, on_click -> onClick). These must never be rendered: a string value would
# become a live inline event handler attribute, which React never renders.
_EVENT_HANDLER_PROP_RE = re.compile(r"^on[A-Za-z]")

# Attributes that may be passed through to the control element for all input components, in
# addition to data-*/aria-* attributes. Anything else that is not explicitly handled is rejected
# with a warning rather than rendered (mirroring how react-aria's filterDOMProps drops unknown
# props, and matching the button renderer's allowlist approach).
_SHARED_CONTROL_PASS_THROUGH_PROPS = frozenset(
    {
        "autoComplete",
        "autoCapitalize",
        "autoCorrect",
        "spellCheck",
        "inputMode",
        "maxLength",
        "minLength",
        "autoFocus",
        "tabIndex",
        "form",
        "enterKeyHint",
        "dir",
        "lang",
        "title",
    }
)


def _is_scalar_prop_value(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


@dataclass
class LabeledInputState:
    """Resolved shared state for input components rendered through ``LabeledInput``."""

    label: Any
    label_position: str
    label_align: str | None
    input_size: str
    is_disabled: bool
    is_readonly: bool
    is_required: bool
    is_invalid: bool
    #: ``valid``/``invalid`` or None. Controls ``data-valid``/``data-invalid`` and the validation icon.
    validation_state: str | None
    is_loading: bool
    description: Any
    error_message: Any
    #: id used on the control; caller supplied or generated when a label is present
    input_id: str | None = None
    description_id: str | None = None
    error_id: str | None = None
    #: full aria-describedby value for the control (generated ids plus any caller supplied value)
    described_by: str | None = None

    @property
    def error_rendered(self) -> bool:
        return bool(self.error_message) and self.is_invalid

    @property
    def description_rendered(self) -> bool:
        # LabeledInput renders the error in place of the description when both would show
        return bool(self.description) and not self.error_rendered


class UILabeledInputRendererMixin(_LabeledInputMixinBase):
    """Shared rendering for components that wrap a control in the ``LabeledInput`` markup.

    Mirrors ``LabeledInput.tsx`` (plus the default ``FormSection`` layout it renders through) from
    ``@alliancesoftware/ui``: an outer wrapper containing the label, the input slot and the help
    text/error message, with state expressed through data attributes.
    """

    #: value used for ``data-apui`` on the control container and generated element id prefixes
    apui_component_name: str

    def generate_html_id(self, context: Context) -> str:
        """Generate a deterministic id, unique within the current template render."""
        render_context = context.render_context
        counter = (render_context.get(_HTML_ID_COUNTER_KEY) or 0) + 1
        render_context[_HTML_ID_COUNTER_KEY] = counter
        return f"apui-{self.apui_component_name}-{counter}"

    def resolve_labeled_input_state(self, context: Context, props: dict[str, Any]) -> LabeledInputState:
        label_position = self.validate_enum_prop(
            props,
            prop_name="labelPosition",
            valid_values=VALID_LABEL_POSITIONS,
            default_value="top",
        )
        label_align = self.validate_optional_enum_prop(
            props,
            prop_name="labelAlign",
            valid_values=VALID_LABEL_ALIGNS,
        )
        input_size = self.validate_enum_prop(
            props,
            prop_name="inputSize",
            valid_values=VALID_INPUT_SIZES,
            default_value="sm",
        )
        validation_state = self.validate_optional_enum_prop(
            props,
            prop_name="validationState",
            valid_values=VALID_VALIDATION_STATES,
        )

        if "disabled" in props and "isDisabled" not in props:
            warnings.warn("You passed 'disabled' - use 'isDisabled' instead")
        is_disabled = bool(props.get("isDisabled") or props.get("disabled"))
        is_readonly = bool(props.get("isReadOnly") or props.get("readOnly"))
        is_required = bool(props.get("isRequired") or props.get("required"))
        is_invalid = bool(props.get("isInvalid")) or validation_state == "invalid"
        if is_invalid and validation_state is None:
            validation_state = "invalid"

        state = LabeledInputState(
            label=props.get("label"),
            label_position=label_position,
            label_align=label_align,
            input_size=input_size,
            is_disabled=is_disabled,
            is_readonly=is_readonly,
            is_required=is_required,
            is_invalid=is_invalid,
            validation_state=validation_state,
            is_loading=bool(props.get("isLoading")),
            description=props.get("description"),
            error_message=props.get("errorMessage"),
        )

        input_id = props.get("id")
        if input_id is None and state.label:
            input_id = self.generate_html_id(context)
        state.input_id = str(input_id) if input_id is not None else None

        if state.description_rendered:
            state.description_id = self.generate_html_id(context)
        if state.error_rendered:
            state.error_id = self.generate_html_id(context)

        described_by_parts = [state.description_id, state.error_id, props.get("aria-describedby")]
        described_by = " ".join(str(part) for part in described_by_parts if part)
        state.described_by = described_by or None
        return state

    def render_labeled_input(
        self,
        context: Context,
        props: dict[str, Any],
        state: LabeledInputState,
        input_slot_html: str,
    ) -> str:
        labeled_input_styles = self.resolve_vanilla_extract_mapping(_LABELED_INPUT_STYLE_PATH)
        form_section_styles = self.resolve_vanilla_extract_mapping(_FORM_SECTION_STYLE_PATH)

        is_side = state.label_position == "side"
        root_class_names = [
            *self.get_recipe_classes(
                labeled_input_styles,
                "labeledInput",
                {"inputSize": state.input_size, "labelPosition": state.label_position},
            ),
            props.get("className"),
        ]
        if is_side:
            # LabeledInput renders through the default FormSection layout which adds its own
            # class for the side label layout
            root_class_names.append(self.get_nested_style_class(form_section_styles, "labeledInput", "side"))

        root_attrs: dict[str, Any] = {
            "data-labeledinput": "1",
            "data-apui": "labeled-input",
            "data-label-position": state.label_position,
            "data-label-align": state.label_align,
            "data-input-size": state.input_size,
            "className": self.join_classes(*root_class_names),
            "style": props.get("style"),
            # Matching getStateDataAttributes usage in LabeledInput; note TextInputBase does not
            # forward isDisabled to LabeledInput so there is no data-disabled at this level (it is
            # set on the input wrapper instead).
            "data-invalid": "true" if state.is_invalid else None,
            "data-required": "true" if state.is_required else None,
            "data-readonly": "true" if state.is_readonly else None,
        }

        label_html = self.render_label(state, labeled_input_styles, form_section_styles)
        help_text_html = self.render_help_text(state, labeled_input_styles)
        input_slot = mark_safe(
            f'<div class="{conditional_escape(self.get_style_class(labeled_input_styles, "input"))}">'
            f"{input_slot_html}</div>"
        )

        if is_side:
            side_wrapper_class = self.get_style_class(form_section_styles, "inputHelpSideWrapper")
            if not label_html:
                # The default FormSection side layout renders a placeholder cell when there is no label
                side_label_class = self.get_nested_style_class(form_section_styles, "label", "side")
                label_html = f'<div class="{conditional_escape(side_label_class)}"></div>'
            children_html = (
                f"{label_html}"
                f'<div class="{conditional_escape(side_wrapper_class)}">{input_slot}{help_text_html}</div>'
            )
        else:
            children_html = f"{label_html}{input_slot}{help_text_html}"

        return self._render_tag("div", root_attrs, children_html)

    def render_label(
        self,
        state: LabeledInputState,
        labeled_input_styles: Any,
        form_section_styles: Any,
    ) -> str:
        if not state.label:
            return ""
        label_styles = self.resolve_vanilla_extract_mapping(_LABEL_STYLE_PATH)
        class_names = [
            self.get_style_class(label_styles, "label"),
            self.get_nested_style_class(labeled_input_styles, "label", state.label_position),
        ]
        if state.label_position == "side":
            class_names.append(self.get_nested_style_class(form_section_styles, "label", "side"))
        if state.label_align == "end":
            class_names.append(self.get_style_class(label_styles, "alignEnd"))

        attrs: dict[str, Any] = {
            "data-apui": "label",
            "data-label-align": state.label_align,
            "className": self.join_classes(*class_names),
            "htmlFor": state.input_id,
        }
        children = conditional_escape(state.label)
        if state.is_required:
            indicator_class = self.get_style_class(label_styles, "requiredIndicator")
            children += mark_safe(
                f'<span aria-hidden="true" class="{conditional_escape(indicator_class)}">*</span>'
            )
        return self._render_tag("label", attrs, children)

    def render_help_text(self, state: LabeledInputState, labeled_input_styles: Any) -> str:
        help_text_class = self.get_style_class(labeled_input_styles, "helpText")
        invalid_class = self.get_style_class(labeled_input_styles, "invalid")
        if state.error_rendered:
            attrs = {
                "className": self.join_classes(help_text_class, invalid_class),
                "id": state.error_id,
            }
            return self._render_tag("div", attrs, conditional_escape(state.error_message))
        if state.description_rendered:
            attrs = {
                "className": self.join_classes(help_text_class, invalid_class if state.is_invalid else None),
                "id": state.description_id,
            }
            return self._render_tag("div", attrs, conditional_escape(state.description))
        return ""

    def render_icon(self, svg_path: str, size: str, extra_class_names: list[str] | None = None) -> str:
        """Render the static markup produced by ``@alliancesoftware/icons`` for an outlined icon."""
        icon_styles = self.resolve_vanilla_extract_mapping(_ICON_STYLE_PATH)
        class_name = self.join_classes(
            self.get_style_class(icon_styles, "icon"),
            self.get_nested_style_class(icon_styles, "variants", "plain"),
            self.get_nested_style_class(icon_styles, "sizes", size),
            *(extra_class_names or []),
        )
        return (
            f'<span role="img" aria-hidden="true" class="{conditional_escape(class_name)}">'
            f"<svg {_SVG_ATTRS}>"
            f'<path d="{svg_path}" {_SVG_PATH_ATTRS}></path>'
            "</svg></span>"
        )


class UITextInputBaseRenderer(UILabeledInputRendererMixin, BaseHtmlUIComponentRenderer):
    """Shared rendering for text-like inputs, mirroring ``TextInputBase.tsx``."""

    #: tag rendered for the actual control
    control_tag = "input"
    #: attrs that may pass through to the control element (plus data-*/aria-*); anything else
    #: not in ``handled_props`` is rejected with a warning
    control_pass_through_props = _SHARED_CONTROL_PASS_THROUGH_PROPS
    #: props consumed by the renderer itself; everything else is passed through or warned about
    handled_props = frozenset(
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
            "disabled",
            "isReadOnly",
            "readOnly",
            "isRequired",
            "required",
            "isLoading",
            "className",
            "inputClassName",
            "style",
            "id",
            "name",
            "value",
            "defaultValue",
            "placeholder",
            "addonBefore",
            "addonAfter",
            "aria-describedby",
            "children",
            "slot",
        }
    )

    def resolve_component_resources(self) -> list[FrontendResource]:
        return [
            self.resolve_frontend_resource(_TEXT_INPUT_BASE_STYLE_PATH),
            self.resolve_frontend_resource(_LABELED_INPUT_STYLE_PATH),
            self.resolve_frontend_resource(_LABEL_STYLE_PATH),
            self.resolve_frontend_resource(_FORM_SECTION_STYLE_PATH),
            self.resolve_frontend_resource(_FOCUS_RING_STYLE_PATH),
            self.resolve_frontend_resource(_ICON_STYLE_PATH),
        ]

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        if children_html.strip():
            warnings.warn(
                f"'{self.apui_component_name}' does not support children; the content will be ignored"
            )
        props = self.filter_unsupported_props(props)
        state = self.resolve_labeled_input_state(context, props)

        text_input_base_styles = self.resolve_vanilla_extract_mapping(_TEXT_INPUT_BASE_STYLE_PATH)
        focus_ring_styles = self.resolve_vanilla_extract_mapping(_FOCUS_RING_STYLE_PATH)

        control_html = self.render_control(context, props, state, text_input_base_styles)

        validation_icon_html = ""
        if state.validation_state and not state.is_disabled:
            icon_path = _CHECK_SVG_PATH if state.validation_state == "valid" else _ALERT_CIRCLE_SVG_PATH
            validation_icon_html = self.render_icon(
                icon_path,
                "xs",
                [
                    self.get_style_class(text_input_base_styles, "adornmentIcon"),
                    self.get_style_class(text_input_base_styles, "validationIcon"),
                ],
            )

        input_wrapper_attrs: dict[str, Any] = {
            "aria-busy": "true" if state.is_loading else None,
            "className": self.join_classes(
                self.get_style_class(text_input_base_styles, "inputWrapper"),
                self.get_style_class(focus_ring_styles, "base"),
            ),
            "data-invalid": "true" if state.validation_state == "invalid" else None,
            "data-valid": "true" if state.validation_state == "valid" else None,
            "data-disabled": "true" if state.is_disabled else None,
            "data-loading": "true" if state.is_loading and not state.is_disabled else None,
        }
        input_wrapper_html = self._render_tag(
            "div", input_wrapper_attrs, f"{control_html}{validation_icon_html}"
        )

        addon_before_html = self.render_addon_before(props, state, text_input_base_styles)
        addon_after_html = self.render_addon_after(props, state, text_input_base_styles)

        container_attrs: dict[str, Any] = {
            "data-apui": self.apui_component_name,
            **self.get_container_extra_attrs(props, state),
            "className": self.join_classes(
                self.get_style_class(text_input_base_styles, "inputContainer"),
                self.get_nested_style_class(text_input_base_styles, "sizes", state.input_size),
            ),
            "data-size": state.input_size,
            "data-element": "textarea" if self.control_tag == "textarea" else "input",
            "data-has-addon-before": "true" if addon_before_html else None,
            "data-has-addon-after": "true" if addon_after_html else None,
        }
        container_html = self._render_tag(
            "div",
            container_attrs,
            f"{addon_before_html}{input_wrapper_html}{addon_after_html}",
        )

        labeled_input_html = self.render_labeled_input(context, props, state, container_html)
        return mark_safe(f"{labeled_input_html}{self.render_after_root(props, state)}")

    def filter_unsupported_props(self, props: dict[str, Any]) -> dict[str, Any]:
        filtered: dict[str, Any] = {}
        for key, value in props.items():
            if value is None:
                # Treat None the same as an unset prop, mirroring undefined in JSX
                continue
            if key in _REACT_ONLY_PROPS:
                warnings.warn(f"Prop '{key}' is not supported by HTML ui components and will be ignored")
                continue
            if _EVENT_HANDLER_PROP_RE.match(key):
                warnings.warn(
                    f"Event handler prop '{key}' is not supported by HTML ui components and will be ignored"
                )
                continue
            if key == "style":
                if not isinstance(value, (str, dict)):
                    warnings.warn("Prop 'style' must be a string or dict; it will be ignored")
                    continue
            elif not _is_scalar_prop_value(value) and not self.allow_non_scalar_prop(key, value):
                warnings.warn(
                    f"Prop '{key}' with non-scalar value is not supported by HTML ui components "
                    "and will be ignored"
                )
                continue
            filtered[key] = value
        return filtered

    def allow_non_scalar_prop(self, key: str, value: Any) -> bool:
        return False

    def get_container_extra_attrs(self, props: dict[str, Any], state: LabeledInputState) -> dict[str, Any]:
        return {}

    def render_addon_before(
        self, props: dict[str, Any], state: LabeledInputState, text_input_base_styles: Any
    ) -> str:
        addon = props.get("addonBefore")
        if not addon:
            return ""
        addon_class = self.get_style_class(text_input_base_styles, "addonBefore")
        return f'<div class="{conditional_escape(addon_class)}">{conditional_escape(addon)}</div>'

    def render_addon_after(
        self, props: dict[str, Any], state: LabeledInputState, text_input_base_styles: Any
    ) -> str:
        addon = props.get("addonAfter")
        if not addon:
            return ""
        addon_class = self.get_style_class(text_input_base_styles, "addonAfter")
        return f'<div class="{conditional_escape(addon_class)}">{conditional_escape(addon)}</div>'

    def render_after_root(self, props: dict[str, Any], state: LabeledInputState) -> str:
        return ""

    def get_base_control_attrs(
        self, props: dict[str, Any], state: LabeledInputState, text_input_base_styles: Any
    ) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "name": props.get("name"),
            "placeholder": props.get("placeholder"),
            "disabled": state.is_disabled,
            "readOnly": state.is_readonly,
            "aria-required": "true" if state.is_required else None,
            "aria-invalid": "true" if state.is_invalid else None,
            "id": state.input_id,
            "aria-describedby": state.described_by,
            "className": self.join_classes(
                self.get_style_class(text_input_base_styles, "input"),
                props.get("inputClassName"),
            ),
        }
        for key, value in props.items():
            if key in self.handled_props:
                continue
            if key in attrs:
                continue
            if key.startswith("data-") or key.startswith("aria-"):
                attrs[key] = value
                continue
            if key in self.control_pass_through_props:
                attrs[key] = value
                continue
            warnings.warn(
                f"Prop '{key}' is not a supported '{self.apui_component_name}' attribute and will be ignored"
            )
        return attrs

    def render_control(
        self,
        context: Context,
        props: dict[str, Any],
        state: LabeledInputState,
        text_input_base_styles: Any,
    ) -> str:
        raise NotImplementedError


class UITextInputRenderer(UITextInputBaseRenderer):
    apui_component_name = "text-input"
    handled_props = UITextInputBaseRenderer.handled_props | {"type"}
    control_pass_through_props = _SHARED_CONTROL_PASS_THROUGH_PROPS | {"pattern", "size", "list"}

    def render_control(
        self,
        context: Context,
        props: dict[str, Any],
        state: LabeledInputState,
        text_input_base_styles: Any,
    ) -> str:
        value = props.get("value")
        if value is None:
            value = props.get("defaultValue")
        attrs: dict[str, Any] = {
            "type": props.get("type", "text"),
            **self.get_base_control_attrs(props, state, text_input_base_styles),
            # React always renders the value attribute (inputs are controlled), including when empty
            "value": "" if value is None else value,
        }
        return mark_safe(f"<input{self.build_attrs_string(attrs)}/>")


class UITextAreaRenderer(UITextInputBaseRenderer):
    apui_component_name = "text-area"
    control_tag = "textarea"
    handled_props = UITextInputBaseRenderer.handled_props | {"height", "type"}
    control_pass_through_props = _SHARED_CONTROL_PASS_THROUGH_PROPS | {"rows", "cols", "wrap"}

    def render_control(
        self,
        context: Context,
        props: dict[str, Any],
        state: LabeledInputState,
        text_input_base_styles: Any,
    ) -> str:
        attrs = self.get_base_control_attrs(props, state, text_input_base_styles)
        height = props.get("height")
        if height is not None:
            if isinstance(height, (int, float)) and not isinstance(height, bool):
                height = f"{height}px"
            attrs["style"] = {"height": height}
        value = props.get("value")
        if value is None:
            value = props.get("defaultValue")
        content = conditional_escape(value) if value is not None else ""
        return mark_safe(f"<textarea{self.build_attrs_string(attrs)}>{content}</textarea>")


class UINumberInputRenderer(UITextInputBaseRenderer):
    apui_component_name = "number-input"
    handled_props = UITextInputBaseRenderer.handled_props | {
        "type",
        "minValue",
        "maxValue",
        "step",
        "hideStepButtons",
        "formatOptions",
        "locale",
    }

    def resolve_component_resources(self) -> list[FrontendResource]:
        return [
            *super().resolve_component_resources(),
            self.resolve_frontend_resource(_NUMBER_INPUT_STYLE_PATH),
        ]

    def allow_non_scalar_prop(self, key: str, value: Any) -> bool:
        # formatOptions is dict valued; it gets its own more specific warning in render_control
        return key == "formatOptions"

    def get_container_extra_attrs(self, props: dict[str, Any], state: LabeledInputState) -> dict[str, Any]:
        # useNumberField renders the container as a labelled group
        return {
            "role": "group",
            "aria-disabled": "true" if state.is_disabled else "false",
            "aria-invalid": "true" if state.is_invalid else None,
        }

    def format_number_value(self, value: Any) -> str:
        """Format a numeric value the way the React component displays it.

        Locale specific formatting (e.g. thousand separators, ``formatOptions``) is not supported
        in the static renderer.
        """
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    def render_control(
        self,
        context: Context,
        props: dict[str, Any],
        state: LabeledInputState,
        text_input_base_styles: Any,
    ) -> str:
        if props.get("formatOptions") is not None:
            warnings.warn("'formatOptions' cannot be mapped to static HTML attributes and will be ignored")
        if props.get("locale") is not None:
            warnings.warn("'locale' is not supported by the static number_input renderer; ignoring")

        value = props.get("value")
        if value is None:
            value = props.get("defaultValue")
        attrs: dict[str, Any] = {
            "aria-disabled": "true" if state.is_disabled else None,
            **self.get_base_control_attrs(props, state, text_input_base_styles),
            "type": "text",
            "autoComplete": "off",
            "inputMode": "numeric",
            "autoCorrect": "off",
            "spellCheck": "false",
            "aria-roledescription": "Number field",
            "value": self.format_number_value(value),
        }
        # The field name is submitted through the hidden input rendered after the root element,
        # not the visible input showing the display value (matching the React component)
        attrs["name"] = None
        return mark_safe(f"<input{self.build_attrs_string(attrs)}/>")

    def render_addon_after(
        self, props: dict[str, Any], state: LabeledInputState, text_input_base_styles: Any
    ) -> str:
        # NumberInput always renders the addonAfter container: it holds the caller addon (if any)
        # followed by the step buttons (unless hidden). Note this means data-has-addon-after is
        # always set, matching the React component.
        addon = props.get("addonAfter")
        addon_content = conditional_escape(addon) if addon else ""
        step_buttons_html = "" if props.get("hideStepButtons") else self.render_step_buttons(props, state)
        addon_class = self.get_style_class(text_input_base_styles, "addonAfter")
        return f'<div class="{conditional_escape(addon_class)}">{addon_content}{step_buttons_html}</div>'

    def render_step_buttons(self, props: dict[str, Any], state: LabeledInputState) -> str:
        number_input_styles = self.resolve_vanilla_extract_mapping(_NUMBER_INPUT_STYLE_PATH)
        container_class = self.get_style_class(number_input_styles, "stepButtonContainer")
        button_class = self.get_nested_style_class(number_input_styles, "stepButton", "default")

        buttons = []
        for direction, aria_label_prefix, icon_path in (
            ("up", "Increase", _CHEVRON_UP_SVG_PATH),
            ("down", "Decrease", _CHEVRON_DOWN_SVG_PATH),
        ):
            aria_label = aria_label_prefix
            if state.label:
                aria_label = f"{aria_label_prefix} {state.label}"
            attrs: dict[str, Any] = {
                "type": "button",
                "disabled": state.is_disabled,
                "tabindex": "-1",
                "aria-label": aria_label,
                "aria-controls": state.input_id,
                "className": button_class,
                "data-direction": direction,
            }
            buttons.append(self._render_tag("button", attrs, self.render_icon(icon_path, "xxs")))
        return f'<div class="{conditional_escape(container_class)}">{"".join(buttons)}</div>'

    def render_after_root(self, props: dict[str, Any], state: LabeledInputState) -> str:
        name = props.get("name")
        if not name:
            return ""
        value = props.get("value")
        if value is None:
            value = props.get("defaultValue")
        attrs: dict[str, Any] = {
            "type": "hidden",
            "name": name,
            "value": self.format_number_value(value),
        }
        return f"<input{self.build_attrs_string(attrs)}/>"
