from __future__ import annotations

from tests.parity.base import HtmlUIParityTestCase
from tests.parity.normalizers import normalize_html_fragment


class UIButtonGroupParityTestCase(HtmlUIParityTestCase):
    fixture_component = "button_group"

    def test_fixture_cases(self):
        fixture = self.load_fixture()
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                self.assert_parity_case(case)

    def test_runtime_is_marked_for_collected_external_auto_attachment(self):
        with self.setup_render_context() as _asset_context:
            output = self.render_ui_template(
                '{% ui "button_group" %}{% ui "button" %}One{% endui %}{% endui %}'
            )
        normalized = normalize_html_fragment(output)
        self.assertIn('data-apui-attach="smart-orientation"', normalized)
        self.assertNotIn("<script", normalized)
