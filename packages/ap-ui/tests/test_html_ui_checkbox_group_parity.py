from __future__ import annotations

from tests.parity.base import HtmlUIParityTestCase


class UICheckboxGroupParityTestCase(HtmlUIParityTestCase):
    fixture_component = "checkbox_group"

    def test_fixture_cases(self):
        fixture = self.load_fixture()
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                # meta.context holds what the template needs, such as a list of checked values
                self.assert_parity_case(case, case["meta"].get("context"))
