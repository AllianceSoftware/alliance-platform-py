from __future__ import annotations

import warnings

from alliance_platform.frontend.renderable_content import RenderableContent
from alliance_platform.ui.templatetags.alliance_platform.html_components.content import render_content
from django import forms
from django.template import Context
from django.template import Origin
from django.utils.safestring import mark_safe

from tests.parity.base import HtmlUIParityTestCase

origin = Origin("UNKNOWN")


class RenderContentTestCase(HtmlUIParityTestCase):
    """Unit tests for the static rendering of renderable content values."""

    def render_value(self, value):
        with self.setup_render_context():
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                output = render_content(value, Context(), prop_name="description")
        return output, [str(item.message) for item in caught_warnings]

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


class StaticInputRichContentTestCase(HtmlUIParityTestCase):
    """Integration of renderable content with the static input renderer."""

    def test_description_accepts_renderable_content(self):
        with self.setup_render_context():
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                output = self.render_ui_template(
                    '{% ui "text_input" label="Email" description=description %}{% endui %}',
                    {"description": RenderableContent.from_html("Use <strong>bold</strong> text", origin)},
                )
        self.assertEqual([str(item.message) for item in caught_warnings], [])
        self.assertIn(
            '<div class="LabeledInput_helpText" id="apui-text-input-2">Use <strong>bold</strong> text</div>',
            output,
        )
        # The description id is wired into aria-describedby as for plain text descriptions
        self.assertIn('aria-describedby="apui-text-input-2"', output)

    def test_description_renderable_content_event_attributes_dropped(self):
        with self.setup_render_context():
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                output = self.render_ui_template(
                    '{% ui "text_input" label="Email" description=description %}{% endui %}',
                    {
                        "description": RenderableContent.from_html(
                            '<span onclick="alert(1)">Help</span>', origin
                        )
                    },
                )
        self.assertNotIn("onclick", output)
        self.assertIn("<span>Help</span>", output)
        self.assertTrue(any("event handler attribute" in str(item.message) for item in caught_warnings))

    def test_form_input_help_text_renders_through_static_widget(self):
        with self.setup_render_context():
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                output = self.render_ui_template(
                    "{% load alliance_platform.form %}"
                    "{% form my_form %}{% form_input my_form.email %}{% endform %}",
                    {"my_form": HelpTextForm()},
                )
        self.assertEqual([str(item.message) for item in caught_warnings], [])
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
