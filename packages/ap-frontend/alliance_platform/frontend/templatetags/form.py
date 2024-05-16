from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
import warnings

from allianceutils.template import parse_tag_arguments
from allianceutils.template import resolve
from django import template
from django.forms import BaseForm
from django.forms import BoundField
from django.template import NodeList
from django.template import Origin
from django.template import TemplateSyntaxError
from django.template.base import UNKNOWN_SOURCE
from django.template.base import FilterExpression

from ..forms.renderers import FormInputContextRenderer
from .react import convert_html_string

register = template.Library()


class _NOT_PROVIDED:
    pass


class FormInputNode(template.Node):
    origin: Origin
    show_valid_state: FilterExpression | bool
    help_text: FilterExpression | str | type[_NOT_PROVIDED]
    label: FilterExpression | str | type[_NOT_PROVIDED]
    is_required: FilterExpression | bool
    extra_attrs: dict[str, FilterExpression]

    def __init__(
        self,
        field: FilterExpression,
        origin: Origin | None,
        help_text=_NOT_PROVIDED,
        label=_NOT_PROVIDED,
        is_required=None,
        show_valid_state=True,
        **extra_attrs,
    ):
        self.origin = origin or Origin(UNKNOWN_SOURCE)
        self.show_valid_state = show_valid_state
        self.field = field
        self.help_text = help_text
        self.label = label
        self.required = is_required
        self.extra_attrs = extra_attrs or {}

    def render(self, context: template.Context):
        field: BoundField = self.field.resolve(context)
        form_context = FormContext.get_current(context)
        extra_attrs = {}
        if not isinstance(field.form.renderer, FormInputContextRenderer):
            warnings.warn("form_input tag should only be used with 'FormInputContextRenderer'")
        else:
            help_text = (
                resolve(self.help_text, context) if self.help_text is not _NOT_PROVIDED else field.help_text
            )
            if help_text:
                # Help text can be HTML and django docs make it clear this value is not HTML-escaped.
                help_text = convert_html_string(help_text, self.origin)[0]
            extra_attrs[field.form.renderer.form_input_context_key] = {
                "raw_value": field.value(),
                "extra_widget_props": {
                    "label": resolve(self.label, context) if self.label is not _NOT_PROVIDED else field.label,
                    "errorMessage": ", ".join(str(e) for e in field.errors),
                    "validationState": (
                        "invalid"
                        if field.errors
                        else (
                            "valid"
                            if field.form.is_bound and resolve(self.show_valid_state, context)
                            else None
                        )
                    ),
                    "description": help_text,
                    "isRequired": (
                        resolve(self.required, context) if self.required is not None else field.field.required
                    ),
                    **{key: resolve(value, context) for key, value in self.extra_attrs.items()},
                    **form_context.get_extra_props(field),
                },
            }
            form_context.mark_processed(field.name)
        return field.as_widget(attrs=extra_attrs)  # type: ignore[arg-type] # dict type in form says on str|bool but other types seem to work fine


@register.tag("form_input")
def form_input(parser: template.base.Parser, token: template.base.Token):
    """Renders a form input with additional props supported by alliance-ui

    This sets `label`, `errorMessage`, `validationState`, `description` and `isRequired`. In addition, it may
    set `autoFocus` based on the `auto_focus` setting on the parent `form` tag.

    The following options can be passed to the tag to override defaults:

    - `label` - set the label for the input. If not specified will use ``field.label``.
    - `help_text` - help text to show below the input. If not specified will use ``field.help_text``.
    - `show_valid_state` - if true, will show the 'valid' (i.e. success) state of the input. If not specified will use
      ``False``. For most components in alliance-ui this results in it showing a tick icon and/or rendering green. If
      this is ``False`` only error states will be shown.
    - `is_required` - if true, will show the input as required. If not specified will use the model field ``required``
      setting.

    In addition, you can pass through any extra attributes that should be set on the input. For example, to set an
    addon for an alliance-ui ``TextInput`` you could do the following::

        {% form_input field addonBefore="$" %}

    Note that the attributes supported here depend entirely on the widget. If the widget is a React component, you
    can also pass react components to the tag::

        {% component "core-ui/icons" "Search" as search_icon %}${% endcomponent %}
        {% form_input field addonBefore=search_icon %}

    The additional props are added to the key ``extra_widget_props`` - so the relevant widget template needs to include
    this for the props to be passed through::

        {% component "@alliancesoftware/ui" "TextInput" props=widget.attrs|merge_props:extra_widget_props|html_attr_to_jsx type=widget.type name=widget.name default_value=widget.value %}
        {% endcomponent %}
    """
    tag_name = token.split_contents()[0]
    args, kwargs, target_var = parse_tag_arguments(parser, token, supports_as=True)
    if not len(args) == 1:
        raise TemplateSyntaxError(f"{tag_name} must be passed the form field to render input for")

    return FormInputNode(
        args[0],
        parser.origin,
        **kwargs,
    )


@dataclass
class FormContext:
    form: BaseForm
    #: If true, the first field with errors will be focused or the first field if form not submitted
    auto_focus: bool = False
    processed_fields: list[str] = field(default_factory=list)

    def mark_processed(self, field_name: str):
        self.processed_fields.append(field_name)

    @classmethod
    def get_current(cls, context: template.Context) -> FormContext:
        form_context = context.get("form_context", None)
        if not form_context:
            raise ValueError("form_input tag must be used within a form tag")
        return form_context

    _focused_field: BoundField | None = None

    def get_extra_props(self, field: BoundField):
        extra_props = {}
        if self.auto_focus:
            if self.form.is_bound and field.errors and not self._focused_field:
                self._focused_field = field
                extra_props["auto_focus"] = True
            elif not self.form.is_bound and not self.processed_fields:
                # focus first field
                extra_props["auto_focus"] = True
        return extra_props


class FormNode(template.Node):
    origin: Origin
    form: FilterExpression
    nodelist: NodeList
    auto_focus: FilterExpression | bool

    def __init__(self, form: FilterExpression, nodelist: NodeList, origin: Origin | None, auto_focus=False):
        self.origin = origin or Origin(UNKNOWN_SOURCE)
        self.form = form
        self.nodelist = nodelist
        self.auto_focus = auto_focus

    def render(self, context: template.Context):
        form: BaseForm = resolve(self.form, context)
        with context.push(form_context=FormContext(form, resolve(self.auto_focus, context))):
            return self.nodelist.render(context)


@register.tag("form")
def form(parser: template.base.Parser, token: template.base.Token):
    """Tag to setup a form context for form_input tags

    This tag doesn't render anything itself, it just sets up context for ``form_input`` tags. This is to support
    the ``auto_focus`` behaviour. This works by adding an ``auto_focus`` prop to the first field with errors, or the
    first rendered field if no errors are present.

    Usage::

        {% load form %}

        {% form form auto_focus=True %}
            <form method="post>
            {% for field in form.visible_fields %}
              {% form_input field %}
            {% endfor %}
            </form>
        {% endform %}


    .. note::

        Usage of this tag requires the following settings to be set::

            FORM_RENDERER = "alliance_platform.frontend.forms.renderers.FormInputContextRenderer"

    """
    tag_name = token.split_contents()[0]
    args, kwargs, target_var = parse_tag_arguments(parser, token, supports_as=True)
    if not len(args) == 1:
        raise TemplateSyntaxError(f"{tag_name} must be passed the django form instance")

    nodelist = parser.parse((f"end{tag_name}",))
    parser.delete_first_token()

    return FormNode(
        args[0],
        nodelist,
        parser.origin,
        **kwargs,
    )
