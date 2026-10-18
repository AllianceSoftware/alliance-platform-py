from __future__ import annotations

from tests.parity.base import HtmlUIParityTestCase


class UINativeSelectParityTestCase(HtmlUIParityTestCase):
    fixture_component = "native_select"

    def test_fixture_cases(self):
        fixture = self.load_fixture()
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                # A case may render with template variables, such as a list of values
                self.assert_parity_case(case, case["meta"].get("context"))

    def test_resources_are_registered(self):
        with self.setup_render_context() as asset_context:
            self.render_ui_template('{% ui "native_select" label="Colour" %}<option>Red</option>{% endui %}')
            resource_paths = [str(resource.path) for resource in asset_context.get_resources_for_bundling()]

        for expected_suffix in [
            "@alliancesoftware/ui/components/text-input/TextInputBase.css.ts",
            "@alliancesoftware/ui/components/form/LabeledInput.css.ts",
            "@alliancesoftware/ui/components/form/Label.css.ts",
            "@alliancesoftware/ui/components/form/FormSection.css.ts",
            "@alliancesoftware/ui/styles/base/focusRing.css.ts",
            "@alliancesoftware/icons/Icon.css.ts",
            "@alliancesoftware/ui/components/select/NativeSelect.css.ts",
            "outlined/ChevronDownOutlined.svg",
        ]:
            with self.subTest(resource=expected_suffix):
                self.assertTrue(any(path.endswith(expected_suffix) for path in resource_paths))
