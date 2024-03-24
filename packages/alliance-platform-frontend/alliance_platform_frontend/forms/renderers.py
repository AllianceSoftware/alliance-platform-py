from django.forms.renderers import TemplatesSetting


class form_input_context_key:
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

    This renderer works with ``form_input`` to pass extra context to widgets
    by setting a special key in the ``widget.attrs`` dictionary. The renderer
    then pops this value and adds the contents to the ``context`` that is then
    used to render the template.
    """

    form_input_context_key = form_input_context_key

    def render(self, template_name, context, request=None):
        if "widget" in context and "attrs" in context["widget"]:
            extra_context = context["widget"]["attrs"].pop(form_input_context_key, {})
            # setting a default means templates can assume the value always exists - makes
            # usage with merge_props etc easier
            if "core_ui_props" not in extra_context:
                extra_context["core_ui_props"] = {}
            context.update(extra_context)
        return super().render(template_name, context, request)
