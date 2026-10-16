from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any
from typing import Mapping

from alliance_platform.frontend.util import SSRExclusionMarker
from django import forms
from django.forms.renderers import TemplatesSetting
from django.template.backends.django import Template as DjangoBackendTemplate

#: The directory of Django's own form templates
_DJANGO_FORM_TEMPLATES_DIR = Path(forms.__file__).resolve().parent / "templates"
_DJANGO_INPUT_TEMPLATE = "django/forms/widgets/input.html"
#: Django's widget templates that are an ``{% include %}`` of ``input.html`` and nothing else, so
#: that a project's ``input.html`` renders their widgets
_DJANGO_INPUT_INCLUDING_TEMPLATES = frozenset(
    f"django/forms/widgets/{name}.html"
    for name in (
        "checkbox",
        "color",
        "date",
        "datetime",
        "email",
        "file",
        "hidden",
        "number",
        "password",
        "search",
        "tel",
        "text",
        "time",
        "url",
    )
)


class form_input_context_key(SSRExclusionMarker):
    """This class serves as a unique sentinel value in a form's widget attributes dictionary
    to set special Alliance Platform context values. It serves no purpose except
    as a dictionary key with special handling.
    """

    pass


class FormInputContextRenderer(TemplatesSetting):
    """Renderer to accommodate passing extra context variables to widgets

    Django widget interface provides no way to pass extra context to widget
    templates short of extending the widget class, or adding it to widget.attrs.
    The problem with passing it in widget.attrs it that it's typically passed
    directly through to the widget. Polluting ``attrs`` with extra context is
    problematic both because it's unexpected and because you either just have to
    accept all the values and hope it causes no issues, or filter them out
    which is inconvenient in templates.

    This renderer works with :ttag:`form_input` to pass extra context to widgets
    by setting a special key in the ``widget.attrs`` dictionary. The renderer
    then pops this value and adds the contents to the ``context`` that is then
    used to render the template.
    """

    form_input_context_key = form_input_context_key

    def render(self, template_name, context, request=None):
        from alliance_platform.frontend.templatetags.react import NestedComponentPropAccumulator

        if "widget" in context and "attrs" in context["widget"]:
            # in order to support nested components, ``form_input`` will set the accumulator (which indicates
            # that the widget is a nested component) in the widget.attrs. This renderer will pop it out and
            # pass it through in the root ``context`` that is used by the widget template. This allows the
            # ``component`` to detect that it is a nested component and handle accordingly.
            accumulator = context["widget"]["attrs"].pop(NestedComponentPropAccumulator.context_key, None)
            extra_context = context["widget"]["attrs"].pop(form_input_context_key, {})
            if accumulator:
                extra_context[NestedComponentPropAccumulator.context_key] = accumulator
            # setting a default means templates can assume the value always exists - makes
            # usage with merge_props etc easier
            if "extra_widget_props" not in extra_context:
                extra_context["extra_widget_props"] = {}
            context.update(extra_context)
        return super().render(template_name, context, request)


@cache
def _is_in_django_form_templates(file_name: str) -> bool:
    return Path(file_name).resolve().is_relative_to(_DJANGO_FORM_TEMPLATES_DIR)


def _is_django_form_template(template: Any) -> bool:
    """Whether ``template`` is one of Django's own form templates, loaded by the Django backend."""
    if not isinstance(template, DjangoBackendTemplate):
        return False
    file_name = template.origin.name
    return isinstance(file_name, str) and _is_in_django_form_templates(file_name)


class StaticFormRenderer(FormInputContextRenderer):
    """:class:`FormInputContextRenderer` that renders text, number and text area widgets as static
    ``{% ui %}`` components.

    Where Django's own template would render one of the widgets in
    :attr:`static_widget_templates`, this renders the ap-ui template it maps to instead: a
    ``text_input``, ``number_input`` or ``text_area`` that takes the label, help text and error
    message :ttag:`form_input` passes in ``extra_widget_props``. A template for the widget that the
    project provides anywhere in ``TEMPLATES``, React or static, renders as it would without this
    renderer, as does a template from a backend other than Django's. Django's templates for all of
    these widgets but the text area are an ``{% include %}`` of ``django/forms/widgets/input.html``,
    so a project's ``input.html`` counts as a template for each of them. Every other widget renders
    as it would with :class:`FormInputContextRenderer`.

    Enable it in place of :class:`FormInputContextRenderer`::

        FORM_RENDERER = "alliance_platform.ui.forms.renderers.StaticFormRenderer"
    """

    #: Django's widget templates this renderer replaces, each mapped to the ap-ui template that
    #: replaces it
    static_widget_templates: Mapping[str, str] = {
        "django/forms/widgets/text.html": "alliance_platform/ui/widgets/input.html",
        "django/forms/widgets/email.html": "alliance_platform/ui/widgets/input.html",
        "django/forms/widgets/url.html": "alliance_platform/ui/widgets/input.html",
        "django/forms/widgets/password.html": "alliance_platform/ui/widgets/input.html",
        "django/forms/widgets/tel.html": "alliance_platform/ui/widgets/input.html",
        "django/forms/widgets/search.html": "alliance_platform/ui/widgets/input.html",
        "django/forms/widgets/number.html": "alliance_platform/ui/widgets/number.html",
        "django/forms/widgets/textarea.html": "alliance_platform/ui/widgets/textarea.html",
    }

    def get_template(self, template_name: str) -> Any:
        template = super().get_template(template_name)
        static_template_name = self.static_widget_templates.get(template_name)
        if static_template_name is None or not self._renders_django_template(template_name, template):
            return template
        return super().get_template(static_template_name)

    def _renders_django_template(self, template_name: str, template: Any) -> bool:
        if not _is_django_form_template(template):
            return False
        if template_name in _DJANGO_INPUT_INCLUDING_TEMPLATES:
            return _is_django_form_template(super().get_template(_DJANGO_INPUT_TEMPLATE))
        return True
