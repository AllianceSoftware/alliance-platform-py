from __future__ import annotations

from tests.parity.base import HtmlUIParityTestCase


class UITextAreaParityTestCase(HtmlUIParityTestCase):
    fixture_component = "text_area"
    parity_ignored_attributes = frozenset({"data-apui-attach"})

    def test_fixture_cases(self):
        fixture = self.load_fixture()
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                self.assert_parity_case(case)

    def test_resources_are_registered(self):
        with self.setup_render_context() as asset_context:
            self.render_ui_template('{% ui "text_area" label="Notes" %}{% endui %}')
            resource_paths = [str(resource.path) for resource in asset_context.get_resources_for_bundling()]

        for expected_suffix in [
            "@alliancesoftware/ui/components/text-input/TextInputBase.css.ts",
            "@alliancesoftware/ui/components/form/LabeledInput.css.ts",
            "@alliancesoftware/ui/styles/base/focusRing.css.ts",
            "@alliancesoftware/ui/components/text-input/TextArea.auto.ts",
        ]:
            with self.subTest(resource=expected_suffix):
                self.assertTrue(any(path.endswith(expected_suffix) for path in resource_paths))

    def test_default_height_is_marked_for_auto_grow_attachment(self):
        with self.setup_render_context():
            output = self.render_ui_template('{% ui "text_area" label="Notes" rows=10 cols=40 %}{% endui %}')

        self.assertIn('data-apui-attach="text-area"', output)
        self.assertNotIn('rows="10"', output)
        self.assertNotIn('cols="40"', output)

    def test_explicit_height_is_fixed_and_not_marked_for_attachment(self):
        with self.setup_render_context():
            output = self.render_ui_template(
                '{% ui "text_area" label="Notes" height=120 rows=10 cols=40 %}{% endui %}'
            )

        self.assertIn('style="height: 120px"', output)
        self.assertNotIn("data-apui-attach", output)
        self.assertNotIn('rows="10"', output)
        self.assertNotIn('cols="40"', output)

    def test_auto_grow_runtime_is_embedded_from_collected_assets(self):
        with self.setup_render_context():
            output = self.render_ui_document('{% ui "text_area" label="Notes" %}{% endui %}')

        self.assertIn("TextArea.auto.ts", output)
        self.assertIn("<script src=", output)
