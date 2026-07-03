from __future__ import annotations

from tests.parity.base import HtmlUIParityTestCase


class UINumberInputParityTestCase(HtmlUIParityTestCase):
    fixture_component = "number_input"

    def test_fixture_cases(self):
        fixture = self.load_fixture()
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                self.assert_parity_case(case)

    def test_resources_are_registered(self):
        with self.setup_render_context() as asset_context:
            self.render_ui_template('{% ui "number_input" label="Quantity" %}{% endui %}')
            resource_paths = [str(resource.path) for resource in asset_context.get_resources_for_bundling()]

        for expected_suffix in [
            "@alliancesoftware/ui/components/text-input/TextInputBase.css.ts",
            "@alliancesoftware/ui/components/form/LabeledInput.css.ts",
            "@alliancesoftware/ui/components/number-input/NumberInput.css.ts",
            "@alliancesoftware/ui/styles/base/focusRing.css.ts",
        ]:
            with self.subTest(resource=expected_suffix):
                self.assertTrue(any(path.endswith(expected_suffix) for path in resource_paths))
