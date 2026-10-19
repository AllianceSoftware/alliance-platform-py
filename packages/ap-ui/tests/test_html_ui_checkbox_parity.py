from __future__ import annotations

from tests.parity.base import HtmlUIParityTestCase


class UICheckboxParityTestCase(HtmlUIParityTestCase):
    fixture_component = "checkbox"

    def test_fixture_cases(self):
        fixture = self.load_fixture()
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                self.assert_parity_case(case)

    def test_resources_are_registered(self):
        with self.setup_render_context() as asset_context:
            self.render_ui_template('{% ui "checkbox" %}Accept{% endui %}')
            resource_paths = [str(resource.path) for resource in asset_context.get_resources_for_bundling()]

        for expected_suffix in [
            "@alliancesoftware/ui/components/checkbox/Checkbox.css.ts",
            "@alliancesoftware/ui/components/form/FormSection.css.ts",
        ]:
            with self.subTest(resource=expected_suffix):
                self.assertTrue(any(path.endswith(expected_suffix) for path in resource_paths))
