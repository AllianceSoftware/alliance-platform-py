from __future__ import annotations

import warnings

from tests.parity.base import HtmlUIParityTestCase


class UIInlineAlertParityTestCase(HtmlUIParityTestCase):
    fixture_component = "inline_alert"

    def render_with_warnings(self, template_body: str, context_kwargs=None):
        with self.setup_render_context():
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                output = self.render_ui_template(template_body, context_kwargs)
        return output, [str(item.message) for item in caught_warnings]

    def test_fixture_cases(self):
        fixture = self.load_fixture()
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                self.assert_parity_case(case)

    def test_resources_include_styles_and_every_dynamic_intent_icon(self):
        with self.setup_render_context() as asset_context:
            self.render_ui_template(
                '{% ui "inline_alert" intent=intent %}Message{% endui %}', {"intent": "info"}
            )
            resource_paths = [str(resource.path) for resource in asset_context.get_resources_for_bundling()]

        self.assertTrue(
            any(
                path.endswith("@alliancesoftware/ui/components/inline-alert/InlineAlert.css.ts")
                for path in resource_paths
            )
        )
        self.assertTrue(any(path.endswith("@alliancesoftware/icons/Icon.css.ts") for path in resource_paths))
        for icon_name in (
            "AlertCircleOutlined",
            "AlertTriangleOutlined",
            "CheckCircleOutlined",
            "InfoCircleOutlined",
        ):
            self.assertTrue(
                any(path.endswith(f"static-svg/outlined/{icon_name}.svg") for path in resource_paths)
            )

    def test_document_inlines_the_icon_without_embedding_a_second_image(self):
        with self.setup_render_context():
            output = self.render_ui_document('{% ui "inline_alert" intent="danger" %}Message{% endui %}')

        self.assertEqual(output.count("<svg"), 1)
        self.assertNotIn("<img", output)

    def test_explicit_icon_uses_slot_styling_and_suppresses_the_default(self):
        with self.setup_render_context():
            output = self.render_ui_template(
                '{% ui "inline_alert" %}'
                '{% ui "icon" name="AlertCircleOutlined" %}{% endui %}'
                '{% ui "content" %}News{% endui %}'
                "{% endui %}"
            )

        self.assertEqual(output.count("<svg"), 1)
        self.assertIn('data-alerticon="1"', output)
        self.assertIn("InlineAlert_icon", output)

    def test_button_group_receives_alert_slot_class(self):
        with self.setup_render_context():
            output = self.render_ui_template(
                '{% ui "inline_alert" %}'
                '{% ui "content" %}Retry the request.{% endui %}'
                '{% ui "button_group" %}{% ui "button" variant="link" %}Retry{% endui %}{% endui %}'
                "{% endui %}"
            )

        self.assertIn("InlineAlert_buttonGroup", output)
        self.assertNotIn('data-only-content="true"', output)

    def test_content_clears_alert_slots_for_nested_layout_components(self):
        with self.setup_render_context():
            output = self.render_ui_template(
                '{% ui "inline_alert" hide_icon=True %}'
                '{% ui "content" %}{% ui "heading" %}Nested heading{% endui %}{% endui %}'
                "{% endui %}"
            )

        self.assertIn(
            '<section class="InlineAlert_content"><h3>Nested heading</h3></section>',
            output,
        )

    def test_layout_component_can_select_a_non_default_slot(self):
        with self.setup_render_context():
            output = self.render_ui_template(
                '{% ui "inline_alert" hide_icon=True %}'
                '{% ui "content" slot="header" %}Header-shaped section{% endui %}'
                "{% endui %}"
            )

        self.assertIn('<section class="InlineAlert_header">Header-shaped section</section>', output)
        self.assertNotIn('data-only-content="true"', output)

    def test_pre_dismissed_alert_renders_nothing(self):
        with self.setup_render_context():
            output = self.render_ui_template('{% ui "inline_alert" is_dismissed=True %}Hidden{% endui %}')

        self.assertEqual(output, "")

    def test_invalid_and_interactive_props_warn(self):
        output, caught = self.render_with_warnings(
            '{% ui "inline_alert" intent="urgent" is_dismissable=True on_dismiss=callback %}'
            "Message{% endui %}",
            {"callback": "ignored"},
        )

        self.assertEqual(
            caught,
            [
                "Invalid 'intent' prop passed: urgent",
                "Prop 'isDismissable' will be ignored: dismissible alerts require client-side state and are not supported statically",
                "Prop 'onDismiss' will be ignored: dismissible alerts require client-side state and are not supported statically",
            ],
        )
        self.assertIn('data-intent="default"', output)
