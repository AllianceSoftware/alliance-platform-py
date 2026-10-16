from __future__ import annotations

from tests.parity.base import HtmlUIParityTestCase


class UILabeledInputParityTestCase(HtmlUIParityTestCase):
    fixture_component = "labeled_input"

    def test_fixture_cases(self):
        fixture = self.load_fixture()
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                self.assert_parity_case(case)
