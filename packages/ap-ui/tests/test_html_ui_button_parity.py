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

        self.assertTrue(any(path.endswith("@alliancesoftware/ui/components/button/Button.css.ts") for path in resource_paths))
        self.assertTrue(any(path.endswith("@alliancesoftware/ui/styles/base/focusRing.css.ts") for path in resource_paths))
