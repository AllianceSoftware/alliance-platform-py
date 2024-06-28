from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
import warnings

from allianceutils.template import parse_tag_arguments
from allianceutils.template import resolve
from django import template
from django.forms import BaseForm
from django.forms import BoundField
from django.template import Context
from django.template import Node
from django.template import NodeList
from django.template import Origin
from django.template import TemplateSyntaxError
from django.template.base import UNKNOWN_SOURCE
from django.template.base import FilterExpression

from ..alliance_ui.labeled_input import LabeledInputNode
from ..alliance_ui.utils import get_module_import_source
from ..forms.renderers import FormInputContextRenderer
from .react import ComponentNode
from .react import NestedComponentProp
from .react import NestedComponentPropAccumulator
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
        non_standard_widget=False,
        **extra_attrs,
    ):
        self.origin = origin or Origin(UNKNOWN_SOURCE)
        self.show_valid_state = show_valid_state
        self.field = field
        self.help_text = help_text
        self.label = label
        self.required = is_required
        self.extra_attrs = extra_attrs or {}
        self.non_standard_widget = non_standard_widget

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
                try:
                    # this may return an empty list if the HTML is invalid
                    help_text = convert_html_string(help_text, self.origin)[0]
                except IndexError:
                    help_text = ""
                    warnings.warn(f"Bad help text on field, likely invalid HTML: {help_text}")
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
            if self.non_standard_widget:
                node = LabeledInputNode(
                    self.origin,
                    get_module_import_source("@alliancesoftware/ui", "LabeledInput", False, self.origin),
                    {
                        **extra_attrs[field.form.renderer.form_input_context_key]["extra_widget_props"],
                        "children": [],
                    },
                )
                node.props.update({"children": NodeList([NestedComponentFormWidgetNode(field, self.origin)])})
                return node.render(context)
            if NestedComponentPropAccumulator.context_key in context:
                # If this is used within another React component, we need to defer rendering of the widget so that
                # it has access to the NestedComponentPropAccumulator
                return NestedComponentFormWidgetNode(field, self.origin, extra_attrs).render(context)
        return field.as_widget(attrs=extra_attrs)  # type: ignore[arg-type] # dict type in form says on str|bool but other types seem to work fine


def _replace_nodes_with_str(items: list[str | ComponentNode], separator: str):
    replacements: dict[str, ComponentNode] = {}
    final_items: list[str] = []
    for item in items:
        if isinstance(item, ComponentNode):
            placeholder = f"__form_widget_placeholder({len(replacements)})__"
            replacements[placeholder] = item
            final_items.append(placeholder)
        else:
            final_items.append(item)
    return separator.join(final_items), replacements


class NestedComponentFormWidgetNode(Node):
    field: BoundField
    origin: Origin
    attrs: dict

    def __init__(self, field: BoundField, origin: Origin, attrs: dict | None = None):
        self.field = field
        self.origin = origin
        self.attrs = attrs or {}

    def render(self, context: Context):
        """
        This is a bit of a hack, so some explanation is needed.

        The problem we are solving is that widgets are rendered as standalone templates. This means that
        the contents is not treated as a component child, even though in this case we are treating it as such.

        temp_accumulator is a temporary accumulator that is used to collect the children of the widget as
        it is rendered. Note that we have to pass this through under ``attrs`` to the ``as_widget`` method which
        makes it appear under ``widget.attrs`` in the final widget template context. This needs to be at the top
        level however, so we rely on ``FormInputContextRenderer`` to pop this value and insert it into the context.
        This is the only way to manipulate the final context a widget template gets rendered with, otherwise you
        can only change ``widget.attrs``. ``FormInputContextRenderer`` is checked in ``FormInputNode`` so it's
        guaranteed to be used if this code path gets executed.

        This is necessary because the widget may contain nested components that need to be
        rendered within the context of the parent component (i.e. we don't want the <script> tags etc, we
        want it to get added to the ``accumulator`` above.

        However, there could be other HTML mixed in with those components so we have to do it in two passes.
        The first pass renders the widgets, collects any nested components and replaces them with placeholders.
        The second passes the first output through ``convert_html_string`` to generate a list of components (where
        HTML tags are encountered), or strings otherwise.

        Take for example this template. It has a mixture of component nodes that will be handled in first pass,
        HTML handled in second pass, and plain strings that require no transformation:

            {% component "@alliancesoftware/ui" "TextInput" props=widget.attrs %}{% endcomponent %}
            Plain text <strong>Nested HTML</strong> More text <span>Extra</span>
            {% component "i" %}Another Component{% endcomponent %}
            End

        ``widget_html`` will be:

            __NestedComponentPropAccumulator__prop__0
            Plain text <strong>Nested HTML</strong> More text <span>Extra</span>
            __NestedComponentPropAccumulator__prop__1
            End

        ``convert_html_string`` will return:

            [
              '__NestedComponentPropAccumulator__prop__0\nPlain text ',
              ComponentNode(CommonComponentSource(name='strong'), {'children': ['Nested HTML']}),
              ' More text ',
              ComponentNode(CommonComponentSource(name='span'), {'children': ['Extra']}),
              '\n__NestedComponentPropAccumulator__prop__1\nEnd'
            ]

        Next we replace any `ComponentNode` with a placeholder (__form_widget_placeholder(0)__) using ``_replace_nodes_with_str``
        which generates a string like:

            __NestedComponentPropAccumulator__prop__0
            Plain text __form_widget_placeholder(0)__ More text __form_widget_placeholder(1)__
            __NestedComponentPropAccumulator__prop__1
            End

        This gets passed through ``temp_accumulator.apply`` which will replace any of the placeholders from first
        pass ("__NestedComponentPropAccumulator__prop__0" in the example). This results in:

            [
                NestedComponentProp(ImportComponentSource(TextInput), ComponentProps({..})),
                '\nPlain text __form_widget_placeholder(0)__ More text __form_widget_placeholder(1)__\n',
                 NestedComponentProp(CommonComponentSource(name='i'), ComponentProps({'children': 'Another Component'})),
                 '\nEnd'
            ]

        Finally, we iterate over this list. If a `NestedComponentProp` is encountered, it's added as a child to the
        original parent component with ``accumulator.add`` (this returns a string placeholder). If a string is
        encountered we have to replace any of the __form_widget_placeholder(i)__ placeholders. We do this by getting
        the original component for that placeholder, add it with ``accumulator.add`` and use the placeholder returned
        in place of the original. This is repeated until all placeholders are replaced. This gives us a final
        string like:

            __NestedComponentPropAccumulator__prop__0
            Plain text __NestedComponentPropAccumulator__prop__1 More text __NestedComponentPropAccumulator__prop__2
            __NestedComponentPropAccumulator__prop__3
            End

        This is what we return, and the parent component will replace any of the remaining placeholders as part of
        the normal ``ComponentNode`` rendering.
        """

        # This is the parent component accumulator we are rendered within. This ``render`` method is being called
        # from within ``ComponentNode`` within an active NestedComponentPropAccumulator context.
        accumulator = context.get(NestedComponentPropAccumulator.context_key)
        if not accumulator:
            raise ValueError("Unexpected: NestedComponentPropAccumulator not found in context")

        with NestedComponentPropAccumulator(context, accumulator.origin_node) as temp_accumulator:
            widget_html = self.field.as_widget(
                attrs={**self.attrs, NestedComponentPropAccumulator.context_key: temp_accumulator}
            )
            final = []
            # if this string appears in the string then it's going to be lost in the final output, but
            # considering they aren't visible characters it likely doesn't matter.
            # Zero-width Space + Information Separator Four
            separator = "\u200b\u001c"
            combined_str, replacements = _replace_nodes_with_str(
                convert_html_string(widget_html, self.origin), separator
            )
            for item in temp_accumulator.apply(combined_str):
                if isinstance(item, str):
                    for part in item.split(separator):
                        if part in replacements:
                            prop = NestedComponentProp(replacements[part], accumulator.origin_node, context)
                            final.append(accumulator.add(prop))
                        else:
                            final.append(part)
                else:
                    final.append(accumulator.add(item))
            return "".join(final)


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
