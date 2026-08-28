from __future__ import annotations

from tests.parity.base import HtmlUIParityTestCase


class UIButtonParityTestCase(HtmlUIParityTestCase):
    fixture_component = "button"

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
