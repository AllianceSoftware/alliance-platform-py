from __future__ import annotations

from decimal import Decimal

from alliance_platform.frontend.renderable_content import RenderableContent
from alliance_platform.ui.html_components.content import render_content
from django import forms
from django.core.exceptions import ValidationError
from django.template import Context
from django.template import Origin
from django.utils.safestring import mark_safe

from tests.parity.base import HtmlUIParityTestCase

origin = Origin("UNKNOWN")


class RenderContentTestCase(HtmlUIParityTestCase):
    """Unit tests for the static rendering of renderable content values."""

    def render_value(self, value):
        with self.setup_render_context():
            with self.capture_diagnostics() as diagnostics:
                output = render_content(value, Context(), prop_name="description")
        return output, diagnostics

    def test_none_renders_empty(self):
        output, caught = self.render_value(None)
        self.assertEqual(output, "")
        self.assertEqual(caught, [])

    def test_plain_string_is_escaped(self):
        output, _ = self.render_value("<b>text</b>")
        self.assertEqual(output, "&lt;b&gt;text&lt;/b&gt;")

    def test_safe_string_is_preserved(self):
        output, _ = self.render_value(mark_safe("<b>text</b>"))
        self.assertEqual(output, "<b>text</b>")

    def test_renderable_content_element(self):
        output, caught = self.render_value(RenderableContent.from_html("<span>Help</span>", origin))
        self.assertEqual(output, "<span>Help</span>")
        self.assertEqual(caught, [])

    def test_renderable_content_mixed_preserves_order(self):
        output, _ = self.render_value(RenderableContent.from_html("Use <strong>bold</strong> text", origin))
        self.assertEqual(output, "Use <strong>bold</strong> text")

    def test_renderable_content_attributes_rendered_with_html_names(self):
        output, _ = self.render_value(
            RenderableContent.from_html('<a href="/docs/" class="hint" target="_blank">Docs</a>', origin)
        )
        self.assertEqual(output, '<a href="/docs/" class="hint" target="_blank">Docs</a>')

    def test_renderable_content_text_is_escaped(self):
        output, _ = self.render_value(RenderableContent.from_html("<span>a &amp; b < c</span>", origin))
        self.assertEqual(output, "<span>a &amp; b &lt; c</span>")

    def test_renderable_content_void_elements(self):
        output, _ = self.render_value(RenderableContent.from_html("before<br>after", origin))
        self.assertEqual(output, "before<br/>after")

    def test_event_handler_attributes_are_dropped_with_warning(self):
        output, caught = self.render_value(
            RenderableContent.from_html('<span onclick="alert(1)">Help</span>', origin)
        )
        self.assertEqual(output, "<span>Help</span>")
        self.assertIn(
            "Renderable content prop 'description' contains event handler attribute 'onclick' "
            "which will not be rendered by static HTML ui components",
            caught,
        )

    def test_event_handler_attributes_on_void_elements_are_dropped(self):
        output, caught = self.render_value(
            RenderableContent.from_html('<input oninput="alert(2)" name="x">', origin)
        )
        self.assertEqual(output, '<input name="x"/>')
        self.assertTrue(any("event handler attribute 'oninput'" in message for message in caught))

    def test_boolean_attributes_render_bare(self):
        output, _ = self.render_value(RenderableContent.from_html('<input name="x" disabled>', origin))
        self.assertEqual(output, '<input name="x" disabled/>')

    def test_numbers_render_as_text(self):
        for value, expected in [(5, "5"), (2.5, "2.5"), (Decimal("12.50"), "12.50")]:
            with self.subTest(value=value):
                output, caught = self.render_value(value)
                self.assertEqual(output, expected)
                self.assertEqual(caught, [])

    def test_list_values_render_each_item(self):
        output, _ = self.render_value(["one ", RenderableContent.from_html("<em>two</em>", origin)])
        self.assertEqual(output, "one <em>two</em>")

    def test_unsupported_value_warns_and_drops(self):
        output, caught = self.render_value(object())
        self.assertEqual(output, "")
        self.assertTrue(any("contains a object value" in message for message in caught))


class UIHelpTextWidget(forms.TextInput):
    template_name = "test_widgets/ui_text_input.html"


class RawDescriptionWidget(forms.TextInput):
    """Widget template that outputs ``extra_widget_props.description`` directly."""

    template_name = "test_widgets/raw_description.html"


class RawErrorMessageWidget(forms.TextInput):
    """Widget template that outputs ``extra_widget_props.errorMessage`` directly."""

    template_name = "test_widgets/raw_error_message.html"


class HelpTextForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        help_text="Use your <strong>work</strong> email",
        widget=UIHelpTextWidget,
    )
    plain = forms.CharField(
        label="Plain", help_text="No markup here", widget=UIHelpTextWidget, required=False
    )
    raw = forms.CharField(
        label="Raw", help_text="No markup here", widget=RawDescriptionWidget, required=False
    )


class SafeErrorForm(forms.Form):
    """A form whose fields fail validation with an error marked safe, a plain one, or both."""

    safe = forms.CharField(label="Safe", widget=UIHelpTextWidget, required=False)
    plain = forms.CharField(label="Plain", widget=UIHelpTextWidget, required=False)
    both = forms.CharField(label="Both", widget=UIHelpTextWidget, required=False)
    raw_plain = forms.CharField(label="Raw", widget=RawErrorMessageWidget, required=False)

    def clean_safe(self):
        raise ValidationError(mark_safe("Use <strong>letters</strong>"))

    def clean_plain(self):
        raise ValidationError("Use <b>letters</b>")

    def clean_both(self):
        raise ValidationError([mark_safe("Use <strong>letters</strong>"), "not <b>digits</b>"])

    def clean_raw_plain(self):
        raise ValidationError("Use letters & digits")


class StaticInputRichContentTestCase(HtmlUIParityTestCase):
    """Integration of renderable content with the static input renderer."""

    def render_with_diagnostics(
        self, template_body: str, context: dict | None = None
    ) -> tuple[str, list[str]]:
        with self.setup_render_context():
            with self.capture_diagnostics() as diagnostics:
                output = self.render_ui_template(template_body, context)
        return output, diagnostics

    def test_addons_accept_rich_content(self):
        output, diagnostics = self.render_with_diagnostics(
            '{% ui "icon" name="CheckOutlined" as icon %}'
            '{% ui "text_input" label="Email" addon_before=icon addon_after=after %}',
            {"after": ["@", RenderableContent.from_html("<em>example.com</em>", origin)]},
        )
        self.assertEqual(diagnostics, [])
        self.assertIn(
            '<div class="TextInputBase_addonBefore"><span role="img" aria-hidden="true" data-apui-slot="icon" '
            'class="Icon_icon" data-size="xs" data-variant="plain"><svg',
            output,
        )
        self.assertIn('</svg>\n</span></div><div class="TextInputBase_inputWrapper', output)
        self.assertIn('<div class="TextInputBase_addonAfter">@<em>example.com</em></div>', output)
        self.assertIn('data-has-addon-before="true" data-has-addon-after="true"', output)

    def test_number_input_addon_after_accepts_rich_content(self):
        output, diagnostics = self.render_with_diagnostics(
            '{% ui "number_input" label="Weight" addon_after=unit %}',
            {"unit": RenderableContent.from_html("<abbr>kg</abbr>", origin)},
        )
        self.assertEqual(diagnostics, [])
        self.assertIn(
            '<div class="TextInputBase_addonAfter"><abbr>kg</abbr><div class="NumberInput_stepButtonContainer">',
            output,
        )

    def test_error_message_accepts_rich_content(self):
        for component in ("text_input", "number_input", "text_area"):
            with self.subTest(component=component):
                output, diagnostics = self.render_with_diagnostics(
                    f'{{% ui "{component}" label="Code" id="id_code" is_invalid=True error_message=error %}}',
                    {"error": RenderableContent.from_html("Use <strong>letters</strong>", origin)},
                )
                self.assertEqual(diagnostics, [])
                self.assertIn(
                    '<div class="LabeledInput_helpText" id="id_code_error">Use <strong>letters</strong></div>',
                    output,
                )

    def test_numeric_addons_render_as_text(self):
        output, diagnostics = self.render_with_diagnostics(
            '{% ui "text_input" label="Weight" addon_after=max_weight %}', {"max_weight": 100}
        )
        self.assertEqual(diagnostics, [])
        self.assertIn('<div class="TextInputBase_addonAfter">100</div>', output)

    def test_plain_addons_and_error_messages_are_escaped(self):
        # Through variables: Django marks string literals in a template safe
        output, diagnostics = self.render_with_diagnostics(
            '{% ui "text_input" label="Price" addon_before=addon error_message=error is_invalid=True %}',
            {"addon": "<b>$</b>", "error": "<b>Bad</b>"},
        )
        self.assertEqual(diagnostics, [])
        self.assertIn('<div class="TextInputBase_addonBefore">&lt;b&gt;$&lt;/b&gt;</div>', output)
        self.assertIn(">&lt;b&gt;Bad&lt;/b&gt;</div>", output)

    def test_rich_addon_event_attributes_dropped(self):
        output, diagnostics = self.render_with_diagnostics(
            '{% ui "text_input" label="Price" addon_before=addon %}',
            {"addon": RenderableContent.from_html('<span onclick="alert(1)">$</span>', origin)},
        )
        self.assertNotIn("onclick", output)
        self.assertIn('<div class="TextInputBase_addonBefore"><span>$</span></div>', output)
        self.assertEqual(
            diagnostics,
            [
                "Renderable content prop 'addonBefore' contains event handler attribute 'onclick' which "
                "will not be rendered by static HTML ui components"
            ],
        )

    def test_form_input_error_marked_safe_renders_as_html_through_static_widget(self):
        output, diagnostics = self.render_with_diagnostics(
            "{% load alliance_platform.form %}{% form my_form %}"
            "{% form_input my_form.safe %}{% form_input my_form.plain %}{% form_input my_form.both %}"
            "{% endform %}",
            {"my_form": SafeErrorForm(data={})},
        )
        self.assertEqual(diagnostics, [])
        self.assertIn('id="id_safe_error">Use <strong>letters</strong></div>', output)
        # An error not marked safe stays text, alone or beside a safe one
        self.assertIn('id="id_plain_error">Use &lt;b&gt;letters&lt;/b&gt;</div>', output)
        self.assertIn(
            'id="id_both_error">Use <strong>letters</strong>, not &lt;b&gt;digits&lt;/b&gt;</div>', output
        )

    def test_form_input_plain_error_message_stays_a_string_for_widget_templates(self):
        with self.setup_render_context():
            output = self.render_ui_template(
                "{% load alliance_platform.form %}"
                "{% form my_form %}{% form_input my_form.raw_plain %}{% endform %}",
                {"my_form": SafeErrorForm(data={})},
            )
        self.assertIn('<span class="raw-error-message">Use letters &amp; digits</span>', output)

    def test_description_accepts_renderable_content(self):
        with self.setup_render_context():
            with self.capture_diagnostics() as diagnostics:
                output = self.render_ui_template(
                    '{% ui "text_input" label="Email" description=description %}',
                    {"description": RenderableContent.from_html("Use <strong>bold</strong> text", origin)},
                )
        self.assertEqual(diagnostics, [])
        self.assertIn(
            '<div class="LabeledInput_helpText" id="apui-text-input-2">Use <strong>bold</strong> text</div>',
            output,
        )
        # The description id is wired into aria-describedby as for plain text descriptions
        self.assertIn('aria-describedby="apui-text-input-2"', output)

    def test_description_renderable_content_event_attributes_dropped(self):
        with self.setup_render_context():
            with self.capture_diagnostics() as diagnostics:
                output = self.render_ui_template(
                    '{% ui "text_input" label="Email" description=description %}',
                    {
                        "description": RenderableContent.from_html(
                            '<span onclick="alert(1)">Help</span>', origin
                        )
                    },
                )
        self.assertNotIn("onclick", output)
        self.assertIn("<span>Help</span>", output)
        self.assertTrue(any("event handler attribute" in message for message in diagnostics))

    def test_form_input_help_text_renders_through_static_widget(self):
        with self.setup_render_context():
            with self.capture_diagnostics() as diagnostics:
                output = self.render_ui_template(
                    "{% load alliance_platform.form %}"
                    "{% form my_form %}{% form_input my_form.email %}{% endform %}",
                    {"my_form": HelpTextForm()},
                )
        self.assertEqual(diagnostics, [])
        self.assertIn("Use your <strong>work</strong> email</div>", output)
        self.assertIn('class="LabeledInput_helpText"', output)
        self.assertIn(">Email", output)
        self.assertIn('name="email"', output)

    def test_form_input_plain_help_text_still_renders(self):
        with self.setup_render_context():
            output = self.render_ui_template(
                "{% load alliance_platform.form %}"
                "{% form my_form %}{% form_input my_form.plain %}{% endform %}",
                {"my_form": HelpTextForm()},
            )
        self.assertIn(">No markup here</div>", output)

    def test_form_input_plain_help_text_stays_a_string_for_widget_templates(self):
        # Widget templates that output extra_widget_props.description directly (rather than
        # passing it to {% component %} or {% ui %}) must keep receiving plain help text as a str
        with self.setup_render_context():
            output = self.render_ui_template(
                "{% load alliance_platform.form %}"
                "{% form my_form %}{% form_input my_form.raw %}{% endform %}",
                {"my_form": HelpTextForm()},
            )
        self.assertIn('<span class="raw-description">No markup here</span>', output)
        self.assertNotIn("RenderableContent", output)
