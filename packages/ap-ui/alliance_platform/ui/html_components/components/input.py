from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
import math
from typing import TYPE_CHECKING
from typing import Any

from alliance_platform.frontend.bundler.frontend_resource import FrontendResource
from alliance_platform.frontend.bundler.frontend_resource import ImageResource
from alliance_platform.ui.icons import get_static_icon_resource
from django.template import Context
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext

from ..base import BaseHtmlUIComponentRenderer
from ..base import enum_prop_rule
from ..base import is_event_handler_attr
from ..content import has_renderable_content
from ..content import is_rich_content_value
from ..content import render_content
from ..render_context import generate_html_id
from ..runtime import add_auto_attach_marker
from ..runtime import resolve_static_runtime_resource
from ..static_icon import ICON_STYLE_PATH

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
_NUMBER_INPUT_STYLE_PATH = "@alliancesoftware/ui/components/number-input/NumberInput.css.ts"

_ALERT_CIRCLE_ICON = "AlertCircleOutlined"
_CHECK_ICON = "CheckOutlined"
_CHEVRON_UP_ICON = "ChevronUpOutlined"
_CHEVRON_DOWN_ICON = "ChevronDownOutlined"

# Props that only make sense with the React runtime (render props, react-aria plumbing). These are
# reported and ignored rather than rendered as attributes.
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

# Rules for the LabeledInput props every component rendering its markup takes
_LABELED_INPUT_PROP_RULES = {
    "labelPosition": enum_prop_rule(VALID_LABEL_POSITIONS, invalid_fallback="top"),
    "labelAlign": enum_prop_rule(VALID_LABEL_ALIGNS),
    "inputSize": enum_prop_rule(VALID_INPUT_SIZES, invalid_fallback="sm"),
    "validationState": enum_prop_rule(VALID_VALIDATION_STATES),
}

# Attributes that may be passed through to the control element for all input components, in
# addition to data-*/aria-* attributes. Anything else that is not explicitly handled is reported
# and dropped rather than rendered (mirroring how react-aria's filterDOMProps drops unknown
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
    #: id of the control: the given one, or a generated one when a label needs it
    input_id: str | None = None
    description_id: str | None = None
    error_id: str | None = None
    #: full aria-describedby value for the control (the help text and error ids plus any caller
    #: supplied value, without duplicates)
    described_by: str | None = None

    @property
    def error_rendered(self) -> bool:
        return has_renderable_content(self.error_message) and self.is_invalid

    @property
    def description_rendered(self) -> bool:
        # LabeledInput renders the error in place of the description when both would show
        return has_renderable_content(self.description) and not self.error_rendered


class UILabeledInputRendererMixin(_LabeledInputMixinBase):
    """Shared rendering for components that wrap a control in the ``LabeledInput`` markup.

    Mirrors ``LabeledInput.tsx`` (plus the default ``FormSection`` layout it renders through) from
    ``@alliancesoftware/ui``: an outer wrapper containing the label, the input slot and the help
    text/error message, with state expressed through data attributes.

    A given control id names the help text ``<id>_helptext`` and the error message ``<id>_error``,
    as Django names a form field's, so the ``aria-describedby`` Django 5.0+ gives a widget points at
    them. Without one they get generated ids.
    """

    #: The prop holding the id of the control: ``id`` on the inputs, which render the control, and
    #: ``inputId`` on ``labeled_input``, whose children render it.
    input_id_prop = "id"
    #: Whether a label without a given control id gets a generated one. Only a renderer that renders
    #: the control can put a generated id on it.
    generate_input_id = True
    #: Whether the root carries ``data-disabled`` for ``isDisabled``. ``LabeledInput`` sets it from
    #: its own ``isDisabled``, which ``TextInputBase`` does not pass it, so the inputs set
    #: ``data-disabled`` on their input wrapper instead.
    root_marks_disabled = False
    #: ``labelAlign`` when none is given. ``LabeledInput`` falls back to the default form layout's
    #: ``"start"``, but ``TextInputBase`` always passes it a ``labelAlign``, undefined when it has
    #: none, so the inputs have no fallback.
    default_label_align: str | None = None
    #: Props that accept rich content as well as plain text, which is escaped: a safe string (such
    #: as a component captured with ``{% ui ... as var %}``), ``RenderableContent`` (such as the
    #: help text and safe error messages ``{% form_input %}`` passes) or a list of these. They
    #: render through :func:`~alliance_platform.ui.html_components.content.render_content`.
    rich_content_props: frozenset[str] = frozenset({"description", "errorMessage"})

    def allow_non_scalar_prop(self, key: str, value: Any) -> bool:
        return key in self.rich_content_props and is_rich_content_value(value)

    def generate_html_id(self, context: Context) -> str:
        """Generate a deterministic id, unique within the current document render."""
        return generate_html_id(context, f"apui-{self.apui_name}")

    def resolve_labeled_input_state(self, context: Context, props: dict[str, Any]) -> LabeledInputState:
        label_position = str(props.get("labelPosition", "top"))
        label_align = props.get("labelAlign", self.default_label_align)
        input_size = str(props.get("inputSize", "sm"))
        validation_state = props.get("validationState")

        is_disabled = bool(props.get("isDisabled"))
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

        # An empty id, as a template variable for a form without auto ids gives, is no id
        given_input_id = props.get(self.input_id_prop) or None
        if given_input_id is not None:
            state.input_id = str(given_input_id)
        elif state.label and self.generate_input_id:
            state.input_id = self.generate_html_id(context)

        if state.description_rendered:
            state.description_id = (
                f"{given_input_id}_helptext" if given_input_id is not None else self.generate_html_id(context)
            )
        if state.error_rendered:
            state.error_id = (
                f"{given_input_id}_error" if given_input_id is not None else self.generate_html_id(context)
            )

        # The aria-describedby Django 5.0+ gives a form widget names the same help text and error
        # ids, so each id is listed once
        parts = (state.description_id, state.error_id, props.get("aria-describedby"))
        described_by = dict.fromkeys(token for part in parts if part for token in str(part).split())
        state.described_by = " ".join(described_by) or None
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
        # LabeledInput.css and FormSection.css style the input size, the label position (including
        # the default FormSection side layout LabeledInput renders through) and the invalid help
        # text colour from these attributes, so the root carries only its own class
        root_attrs: dict[str, Any] = {
            "data-labeledinput": "1",
            "data-apui": "labeled-input",
            "data-label-position": state.label_position,
            "data-label-align": state.label_align,
            "data-input-size": state.input_size,
            "className": self.join_classes(
                self.get_style_class(labeled_input_styles, "labeledInput"), props.get("className")
            ),
            "style": props.get("style"),
            # Matching getStateDataAttributes usage in LabeledInput (see root_marks_disabled)
            "data-invalid": "true" if state.is_invalid else None,
            "data-disabled": "true" if self.root_marks_disabled and state.is_disabled else None,
            "data-required": "true" if state.is_required else None,
            "data-readonly": "true" if state.is_readonly else None,
        }

        label_html = self.render_label(state, labeled_input_styles)
        help_text_html = self.render_help_text(context, state, labeled_input_styles)
        input_slot = mark_safe(
            f'<div class="{conditional_escape(self.get_style_class(labeled_input_styles, "input"))}">'
            f"{input_slot_html}</div>"
        )

        if is_side:
            side_wrapper_class = self.get_style_class(form_section_styles, "inputHelpSideWrapper")
            if not label_html:
                # The default FormSection side layout renders a placeholder cell when there is no label
                placeholder_class = self.get_style_class(form_section_styles, "sideLabelPlaceholder")
                label_html = f'<div class="{conditional_escape(placeholder_class)}"></div>'
            children_html = (
                f"{label_html}"
                f'<div class="{conditional_escape(side_wrapper_class)}">{input_slot}{help_text_html}</div>'
            )
        else:
            children_html = f"{label_html}{input_slot}{help_text_html}"

        return self.render_tag("div", root_attrs, children_html)

    def render_label(self, state: LabeledInputState, labeled_input_styles: Any) -> str:
        if not state.label:
            return ""
        label_styles = self.resolve_vanilla_extract_mapping(_LABEL_STYLE_PATH)
        attrs: dict[str, Any] = {
            "data-apui": "label",
            # Label.css aligns the label to the end from this attribute
            "data-label-align": state.label_align,
            "className": self.join_classes(
                self.get_style_class(label_styles, "label"),
                self.get_style_class(labeled_input_styles, "label"),
            ),
            "htmlFor": state.input_id,
        }
        children = conditional_escape(state.label)
        if state.is_required:
            indicator_class = self.get_style_class(label_styles, "requiredIndicator")
            children += mark_safe(
                f'<span aria-hidden="true" class="{conditional_escape(indicator_class)}">*</span>'
            )
        return self.render_tag("label", attrs, children)

    def render_help_text(self, context: Context, state: LabeledInputState, labeled_input_styles: Any) -> str:
        # The root's data-invalid, set whenever state.is_invalid is, colours the error message and
        # an invalid description
        help_text_class = self.get_style_class(labeled_input_styles, "helpText")
        if state.error_rendered:
            attrs = {"className": help_text_class, "id": state.error_id}
            content = render_content(
                state.error_message,
                context,
                prop_name="errorMessage",
                origin=self.origin,
                component=self.name,
            )
            return self.render_tag("div", attrs, content)
        if state.description_rendered:
            attrs = {"className": help_text_class, "id": state.description_id}
            content = render_content(
                state.description, context, prop_name="description", origin=self.origin, component=self.name
            )
            return self.render_tag("div", attrs, content)
        return ""


class UITextInputBaseRenderer(UILabeledInputRendererMixin, BaseHtmlUIComponentRenderer):
    """Shared rendering for text-like inputs, mirroring ``TextInputBase.tsx``."""

    # text_input, number_input and text_area are leaf tags: no children and no {% endui %}
    has_children = False
    unsupported_prop_reasons = {
        key: "React-only props are not supported by static input components" for key in _REACT_ONLY_PROPS
    }
    allow_data_props = True
    allow_aria_props = True
    deprecated_prop_aliases = {"disabled": "isDisabled"}
    prop_rules = _LABELED_INPUT_PROP_RULES
    prop_filter_context = "static input components"
    event_handler_prop_reason = "event handlers are not supported by static input components"
    prop_docs = {
        "id": (
            "The control's id, which also names the help text ``<id>_helptext`` and the error message "
            "``<id>_error``, as Django names a form field's."
        ),
        "readOnly": "Same as ``is_read_only``, in the HTML attribute's spelling.",
        "required": "Same as ``is_required``, in the HTML attribute's spelling.",
    }

    @classmethod
    def supports_prop_name(cls, key: str) -> bool:
        canonical = cls.canonical_prop_name(key)
        if canonical.startswith(("data-", "aria-")):
            return super().supports_prop_name(canonical)
        return (
            canonical not in cls.unsupported_prop_reasons
            and not is_event_handler_attr(canonical)
            and (
                canonical in cls.handled_props
                or canonical in cls.control_pass_through_props
                or canonical in cls.prop_rules
                or canonical in cls.forwarded_props
            )
        )

    @classmethod
    def documented_props(cls) -> frozenset[str]:
        # supported_props is None: these are the names supports_prop_name accepts
        return cls._documented_prop_names(
            {*cls.handled_props, *cls.control_pass_through_props, *cls.prop_rules, *cls.forwarded_props}
        )

    #: tag rendered for the actual control
    control_tag = "input"
    #: attrs that may pass through to the control element (plus data-*/aria-*); anything else
    #: not in ``handled_props`` is reported and dropped
    control_pass_through_props = _SHARED_CONTROL_PASS_THROUGH_PROPS
    # The addons render rich content too, such as an icon captured with {% ui "icon" ... as icon %}
    rich_content_props = UILabeledInputRendererMixin.rich_content_props | {"addonBefore", "addonAfter"}
    #: props consumed by the renderer itself; everything else is passed through or reported
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
            self.resolve_frontend_resource(ICON_STYLE_PATH),
            get_static_icon_resource(_ALERT_CIRCLE_ICON, origin=self.origin),
            get_static_icon_resource(_CHECK_ICON, origin=self.origin),
        ]

    def get_resources_to_embed(self) -> list[FrontendResource]:
        # Static icons are read and rendered inline; their ImageResources are build dependencies,
        # not standalone document images. Passing them through the embed pipeline emits detached
        # SVG/image elements at the document's asset insertion point.
        return [
            resource
            for resource in self.get_resources_for_bundling()
            if not isinstance(resource, ImageResource)
        ]

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        state = self.resolve_labeled_input_state(context, props)

        text_input_base_styles = self.resolve_vanilla_extract_mapping(_TEXT_INPUT_BASE_STYLE_PATH)
        focus_ring_styles = self.resolve_vanilla_extract_mapping(_FOCUS_RING_STYLE_PATH)

        control_html = self.render_control(context, props, state, text_input_base_styles)

        validation_icon_html = ""
        if self.should_render_validation_icon(props, state):
            icon_name = _CHECK_ICON if state.validation_state == "valid" else _ALERT_CIRCLE_ICON
            validation_icon_html = self.render_icon(
                icon_name,
                "xs",
                [
                    self.get_style_class(text_input_base_styles, "adornmentIcon"),
                    self.get_style_class(text_input_base_styles, "validationIcon"),
                ],
                slot=False,
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
        input_wrapper_html = self.render_tag(
            "div", input_wrapper_attrs, f"{control_html}{validation_icon_html}"
        )

        addon_before_html = self.render_addon_before(context, props, state, text_input_base_styles)
        addon_after_html = self.render_addon_after(context, props, state, text_input_base_styles)

        container_attrs: dict[str, Any] = {
            "data-apui": self.apui_name,
            **self.get_container_extra_attrs(props, state),
            "className": self.get_style_class(text_input_base_styles, "inputContainer"),
            "data-size": state.input_size,
            "data-element": "textarea" if self.control_tag == "textarea" else "input",
            "data-has-addon-before": "true" if addon_before_html else None,
            "data-has-addon-after": "true" if addon_after_html else None,
        }
        self.configure_container_runtime(
            context,
            props,
            state,
            container_attrs,
        )
        container_children_html = f"{addon_before_html}{input_wrapper_html}{addon_after_html}"
        container_html = mark_safe(self.render_tag("div", container_attrs, container_children_html))

        return mark_safe(self.render_labeled_input(context, props, state, container_html))

    def get_container_extra_attrs(self, props: dict[str, Any], state: LabeledInputState) -> dict[str, Any]:
        return {}

    def should_render_validation_icon(self, props: dict[str, Any], state: LabeledInputState) -> bool:
        return bool(state.validation_state) and not state.is_disabled

    def configure_container_runtime(
        self,
        context: Context,
        props: dict[str, Any],
        state: LabeledInputState,
        container_attrs: dict[str, Any],
    ) -> None:
        """Add any runtime-specific state to the container before it is rendered."""

    def render_addon_content(self, context: Context, props: dict[str, Any], prop_name: str) -> str:
        """Render the content of the ``addonBefore`` or ``addonAfter`` prop, ``""`` when there is none."""
        addon = props.get(prop_name)
        if not has_renderable_content(addon):
            return ""
        return render_content(addon, context, prop_name=prop_name, origin=self.origin, component=self.name)

    def render_addon_before(
        self, context: Context, props: dict[str, Any], state: LabeledInputState, text_input_base_styles: Any
    ) -> str:
        addon_content = self.render_addon_content(context, props, "addonBefore")
        if not addon_content:
            return ""
        addon_class = self.get_style_class(text_input_base_styles, "addonBefore")
        return f'<div class="{conditional_escape(addon_class)}">{addon_content}</div>'

    def render_addon_after(
        self, context: Context, props: dict[str, Any], state: LabeledInputState, text_input_base_styles: Any
    ) -> str:
        addon_content = self.render_addon_content(context, props, "addonAfter")
        if not addon_content:
            return ""
        addon_class = self.get_style_class(text_input_base_styles, "addonAfter")
        return f'<div class="{conditional_escape(addon_class)}">{addon_content}</div>'

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
            self.report(
                f"Prop '{key}' is not a supported '{self.name}' attribute and will be ignored",
                kind="contract",
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
    name = "text_input"
    react_tag = 'component "@alliancesoftware/ui" "TextInput"'
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


_TEXT_AREA_SIZE_PROP_DOC = (
    "Accepted, as Django's ``Textarea`` widget sets it, and not rendered, so the text area keeps React's "
    "compact first paint."
)


class UITextAreaRenderer(UITextInputBaseRenderer):
    name = "text_area"
    react_tag = 'component "@alliancesoftware/ui" "TextArea"'
    runtime_token = "text-area"
    control_tag = "textarea"
    handled_props = UITextInputBaseRenderer.handled_props | {"height", "type", "rows", "cols"}
    control_pass_through_props = _SHARED_CONTROL_PASS_THROUGH_PROPS | {"wrap"}
    prop_docs = {
        **UITextInputBaseRenderer.prop_docs,
        "rows": _TEXT_AREA_SIZE_PROP_DOC,
        "cols": _TEXT_AREA_SIZE_PROP_DOC,
        "type": "Accepted and not rendered, as a ``<textarea>`` has no type.",
    }

    def resolve_component_resources(self) -> list[FrontendResource]:
        return [*super().resolve_component_resources(), resolve_static_runtime_resource(self)]

    def configure_container_runtime(
        self,
        context: Context,
        props: dict[str, Any],
        state: LabeledInputState,
        container_attrs: dict[str, Any],
    ) -> None:
        # A fixed height does not auto-grow
        if props.get("height") is not None:
            return
        add_auto_attach_marker(container_attrs, self.runtime_token)

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
        # The HTML parser drops a line break right after <textarea>, so a value starting with one
        # gets another in front, as React writes it. A submitted value's line breaks are CRLF, which
        # the parser reads as one.
        if content.startswith(("\n", "\r")):
            content = f"\n{content}"
        return mark_safe(f"<textarea{self.build_attrs_string(attrs)}>{content}</textarea>")


class UINumberInputRenderer(UITextInputBaseRenderer):
    name = "number_input"
    react_tag = 'component "@alliancesoftware/ui" "NumberInput"'
    runtime_token = "number-input"
    # Django's NumberInput widget sets the native min and max attributes for a field's min_value and
    # max_value, as a number input expects them; NumberInput takes them as minValue and maxValue
    prop_aliases = {"min": "minValue", "max": "maxValue"}
    prop_docs = {
        **UITextInputBaseRenderer.prop_docs,
        "minValue": "``min`` is the attribute Django's ``NumberInput`` widget sets for ``min_value``.",
        "maxValue": "``max`` is the attribute Django's ``NumberInput`` widget sets for ``max_value``.",
        "name": (
            "Rendered on the visible input, so the unformatted number submits without JavaScript; the "
            "runtime moves it to a hidden input when it formats the value."
        ),
        "type": "Accepted and not rendered: the control is always a text input, as in React.",
    }
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
            get_static_icon_resource(_CHEVRON_UP_ICON, origin=self.origin),
            get_static_icon_resource(_CHEVRON_DOWN_ICON, origin=self.origin),
            resolve_static_runtime_resource(self),
        ]

    def allow_non_scalar_prop(self, key: str, value: Any) -> bool:
        # formatOptions is dict valued; it gets its own more specific validation before rendering.
        return key == "formatOptions" or super().allow_non_scalar_prop(key, value)

    def get_container_extra_attrs(self, props: dict[str, Any], state: LabeledInputState) -> dict[str, Any]:
        # useNumberField renders the container as a labelled group
        initial_value = props.get("value")
        if initial_value is None:
            initial_value = props.get("defaultValue")
        return {
            "role": "group",
            "aria-disabled": "true" if state.is_disabled else "false",
            "aria-invalid": "true" if state.is_invalid else None,
            # Static-only configuration consumed by NumberInput.attach.ts. The React component
            # receives these values directly as props instead.
            "data-apui-number-input-min-value": props.get("minValue"),
            "data-apui-number-input-max-value": props.get("maxValue"),
            "data-apui-number-input-step": props.get("step"),
            "data-apui-number-input-locale": props.get("locale"),
            "data-apui-number-input-initial-value": self.format_number_value(initial_value),
            "data-apui-number-input-format-options": self.serialize_format_options(
                props.get("formatOptions")
            ),
        }

    def serialize_format_options(self, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            self.report("Prop 'formatOptions' must be a dict; it will be ignored", kind="contract")
            return None
        try:
            return json.dumps(value, separators=(",", ":"), sort_keys=True)
        except (TypeError, ValueError):
            self.report(
                "Prop 'formatOptions' must contain JSON-serializable values; it will be ignored",
                kind="contract",
            )
            return None

    def should_render_validation_icon(self, props: dict[str, Any], state: LabeledInputState) -> bool:
        # NumberInput's documented contract reserves the input's trailing visual slot for step
        # controls. Validation state still colours the field, but its icon only appears when the
        # step controls are hidden.
        return bool(props.get("hideStepButtons")) and super().should_render_validation_icon(props, state)

    def configure_container_runtime(
        self,
        context: Context,
        props: dict[str, Any],
        state: LabeledInputState,
        container_attrs: dict[str, Any],
    ) -> None:
        add_auto_attach_marker(container_attrs, self.runtime_token)

    def format_number_value(self, value: Any) -> str:
        """Format a numeric value the way the React component displays it.

        Locale-specific display formatting is applied by the attach runtime. The server-rendered
        value, which the visible input submits when the runtime does not run, remains an unformatted
        numeric string.
        """
        if value is None:
            return ""
        if isinstance(value, float) and math.isnan(value):
            return ""
        if isinstance(value, Decimal) and value.is_nan():
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
            "aria-roledescription": gettext("Number field"),
            "value": self.format_number_value(value),
        }
        # The visible input keeps the field name so the unformatted server value and any edits
        # submit natively without JavaScript. When the attach runtime formats the displayed value
        # it moves the name to a hidden input it creates to carry the numeric value instead.
        return mark_safe(f"<input{self.build_attrs_string(attrs)}/>")

    def render_addon_after(
        self, context: Context, props: dict[str, Any], state: LabeledInputState, text_input_base_styles: Any
    ) -> str:
        # The addonAfter container holds the caller addon (if any) followed by the step buttons.
        # When both are absent React returns null so TextInputBase keeps its rounded trailing edge.
        addon_content = self.render_addon_content(context, props, "addonAfter")
        step_buttons_html = "" if props.get("hideStepButtons") else self.render_step_buttons(props, state)
        if not addon_content and not step_buttons_html:
            return ""
        addon_class = self.get_style_class(text_input_base_styles, "addonAfter")
        return f'<div class="{conditional_escape(addon_class)}">{addon_content}{step_buttons_html}</div>'

    def render_step_buttons(self, props: dict[str, Any], state: LabeledInputState) -> str:
        number_input_styles = self.resolve_vanilla_extract_mapping(_NUMBER_INPUT_STYLE_PATH)
        container_class = self.get_style_class(number_input_styles, "stepButtonContainer")
        button_class = self.get_style_class(number_input_styles, "stepButton")

        if state.label:
            aria_labels = {
                "up": gettext("Increase %(label)s") % {"label": state.label},
                "down": gettext("Decrease %(label)s") % {"label": state.label},
            }
        else:
            aria_labels = {"up": gettext("Increase"), "down": gettext("Decrease")}

        buttons = []
        for direction, icon_name in (("up", _CHEVRON_UP_ICON), ("down", _CHEVRON_DOWN_ICON)):
            attrs: dict[str, Any] = {
                "type": "button",
                "disabled": state.is_disabled or state.is_readonly,
                "tabindex": "-1",
                "aria-label": aria_labels[direction],
                "aria-controls": state.input_id,
                "className": button_class,
                "data-direction": direction,
            }
            buttons.append(self.render_tag("button", attrs, self.render_icon(icon_name, "xxs", slot=False)))
        return f'<div class="{conditional_escape(container_class)}">{"".join(buttons)}</div>'


# LabeledInput props with no static equivalent: the props of the elements it renders, a custom label
# element and refs. Reported, with the React tag to use, and ignored.
_LABELED_INPUT_REACT_ONLY_PROPS = frozenset(
    {
        "labelProps",
        "descriptionProps",
        "errorMessageProps",
        "containerProps",
        "elementType",
        "ref",
        "labelRef",
        "inputRef",
        "containerRef",
    }
)


class UILabeledInputRenderer(UILabeledInputRendererMixin, BaseHtmlUIComponentRenderer):
    """Wraps what its children render in the label, help text and error message of ``LabeledInput``.

    Mirrors ``LabeledInput.tsx`` as ``{% LabeledInput %}`` renders it, with the markup the inputs
    render around their own control, for a control its children render: a native ``<select>`` or a
    Django widget, say. ``inputId`` is that control's id: the label's ``for`` and the base of the
    help text and error message ids (``<inputId>_helptext``, ``<inputId>_error``). The renderer does
    not own the control's markup and adds nothing to it; Django 5.0+ points a form widget's
    ``aria-describedby`` at those ids.
    """

    name = "labeled_input"
    react_tag = "LabeledInput"
    input_id_prop = "inputId"
    # The control is the children's, so a generated id could not be put on it
    generate_input_id = False
    root_marks_disabled = True
    default_label_align = "start"
    # The props the inputs put on their control are accepted, so a widget template can pass
    # extra_widget_props whole ({% form_input %} adds autoFocus to it), but not rendered: they
    # belong on the control, which the children render. LabeledInput ignores them too.
    supported_props = (
        frozenset(
            {
                "label",
                "labelPosition",
                "labelAlign",
                "inputSize",
                "isRequired",
                "isInvalid",
                "validationState",
                "isDisabled",
                "isReadOnly",
                "description",
                "errorMessage",
                "inputId",
                "className",
                "style",
            }
        )
        | _SHARED_CONTROL_PASS_THROUGH_PROPS
    )
    allow_data_props = True
    allow_aria_props = True
    unsupported_prop_reasons = {
        key: "React-only props are not supported by static labeled inputs"
        for key in _LABELED_INPUT_REACT_ONLY_PROPS
    }
    # validationState="invalid" sets isInvalid, as {% LabeledInput %} does
    prop_rules = _LABELED_INPUT_PROP_RULES
    prop_filter_context = "static labeled inputs"
    event_handler_prop_reason = "event handlers are not supported by static labeled inputs"
    prop_docs = {
        "inputId": (
            "The id of the control the children render: the label's ``for``, and the base of the help "
            "text and error message ids, ``<input_id>_helptext`` and ``<input_id>_error``."
        ),
        "validationState": (
            '``"invalid"`` sets ``is_invalid``, as ``{% LabeledInput %}`` converts it for '
            "``{% form_input %}``; React's ``LabeledInput`` has no such prop."
        ),
        **dict.fromkeys(
            _SHARED_CONTROL_PASS_THROUGH_PROPS,
            "Accepted so a widget template can pass ``extra_widget_props`` whole, and not rendered: it "
            "belongs on the control the children render.",
        ),
        **dict.fromkeys(
            ("data-*", "aria-*"),
            "Accepted and not rendered: they belong on the control the children render.",
        ),
    }

    def resolve_component_resources(self) -> list[FrontendResource]:
        return [
            self.resolve_frontend_resource(_LABELED_INPUT_STYLE_PATH),
            self.resolve_frontend_resource(_LABEL_STYLE_PATH),
            self.resolve_frontend_resource(_FORM_SECTION_STYLE_PATH),
        ]

    def render_component(self, context: Context, props: dict[str, Any], children_html: str) -> str:
        state = self.resolve_labeled_input_state(context, props)
        if state.label and state.input_id is None:
            self.report(
                "'labeled_input' has a label but no 'input_id', so the label is not associated with "
                "a control: pass the id of the control it wraps",
                kind="contract",
            )
        return self.render_labeled_input(context, props, state, children_html)
