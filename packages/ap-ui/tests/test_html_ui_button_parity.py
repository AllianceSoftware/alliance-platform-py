from __future__ import annotations

import warnings

from tests.parity.base import HtmlUIParityTestCase


class UIButtonParityTestCase(HtmlUIParityTestCase):
    fixture_component = "button"

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

    def test_resources_are_registered(self):
        with self.setup_render_context() as asset_context:
            self.render_ui_template('{% ui "button" %}Save{% endui %}')
            resource_paths = [str(resource.path) for resource in asset_context.get_resources_for_bundling()]

        self.assertTrue(
            any(
                path.endswith("@alliancesoftware/ui/components/button/Button.css.ts")
                for path in resource_paths
            )
        )
        self.assertTrue(
            any(path.endswith("@alliancesoftware/ui/styles/base/focusRing.css.ts") for path in resource_paths)
        )

    def test_explicit_icon_only_supports_multiple_state_wrappers(self):
        with self.setup_render_context():
            output = self.render_ui_template(
                '{% ui "button" is_icon_only=True aria_label="Toggle navigation" %}'
                '<span data-state="closed">Closed</span>'
                '<span data-state="open">Open</span>'
                "{% endui %}"
            )

        self.assertIn('data-icon-only="true"', output)
        self.assertIn('aria-label="Toggle navigation"', output)
        self.assertIn('data-state="closed"', output)
        self.assertIn('data-state="open"', output)

    def test_explicit_false_overrides_automatic_icon_only_detection(self):
        with self.setup_render_context():
            output = self.render_ui_template(
                '{% ui "button" is_icon_only=False aria_label="Approve" %}'
                '{% ui "icon" name="CheckOutlined" %}{% endui %}'
                "{% endui %}"
            )

        self.assertNotIn("data-icon-only", output)

    def test_invalid_enum_props_are_normalized_by_shared_rules(self):
        output, caught = self.render_with_warnings(
            '{% ui "button" variant="raised" color="green" size="huge" shape="square" %}Save{% endui %}'
        )

        self.assertEqual(
            caught,
            [
                "Invalid 'variant' prop passed: raised",
                "Invalid 'color' prop passed: green",
                "Invalid 'size' prop passed: huge",
                "Invalid 'shape' prop passed: square",
            ],
        )
        self.assertIn('data-variant="solid"', output)
        self.assertIn('data-color="primary"', output)
        self.assertIn('data-size="md"', output)
        self.assertIn('data-shape="default"', output)

    def test_unknown_and_event_props_are_dropped_while_dom_props_are_forwarded(self):
        output, caught = self.render_with_warnings(
            '{% ui "button" type="submit" title="Save" data_testid="save" '
            'aria_label="Save changes" unknown_prop="nope" on_click="alert(1)" %}'
            "Save{% endui %}"
        )

        self.assertEqual(
            caught,
            [
                "Prop 'unknownProp' is not a supported 'button' prop and will be ignored",
                "Prop 'onClick' will be ignored: event handlers are not supported by static button components",
            ],
        )
        self.assertIn('type="submit"', output)
        self.assertIn('title="Save"', output)
        self.assertIn('data-testid="save"', output)
        self.assertIn('aria-label="Save changes"', output)
        self.assertNotIn("unknown", output)
        self.assertNotIn("alert", output)

    def test_anchor_forwards_boolean_download_attribute(self):
        output, caught = self.render_with_warnings(
            '{% ui "button" href="/exports/latest/" download=True %}Download{% endui %}'
        )

        self.assertEqual(caught, [])
        self.assertTrue(output.startswith("<a "))
        self.assertIn('href="/exports/latest/"', output)
        self.assertIn(" download ", output)
        self.assertNotIn('download="', output)

    def test_anchor_forwards_filename_download_attribute(self):
        output, caught = self.render_with_warnings(
            '{% ui "button" href="/exports/latest/" download="waste-composition.csv" %}Download{% endui %}'
        )

        self.assertEqual(caught, [])
        self.assertTrue(output.startswith("<a "))
        self.assertIn('href="/exports/latest/"', output)
        self.assertIn('download="waste-composition.csv"', output)

    def test_invalid_element_type_cannot_change_the_tag_structure(self):
        output, caught = self.render_with_warnings(
            '{% ui "button" element_type=element_type %}Save{% endui %}',
            {"element_type": 'button><script data-bad="1"'},
        )

        self.assertEqual(
            caught,
            ["Invalid 'elementType' prop passed: button><script data-bad=\"1\""],
        )
        self.assertTrue(output.startswith("<button "))
        self.assertNotIn("<script", output)

    def test_deprecated_disabled_alias_does_not_override_canonical_prop(self):
        output, caught = self.render_with_warnings(
            '{% ui "button" disabled=True is_disabled=False %}Save{% endui %}'
        )

        self.assertEqual(caught, ["You passed 'disabled' - use 'isDisabled' instead"])
        self.assertNotIn("data-disabled", output)
        self.assertNotIn(" disabled", output)
