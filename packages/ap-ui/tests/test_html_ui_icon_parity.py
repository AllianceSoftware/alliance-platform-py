from __future__ import annotations

from tests.parity.base import HtmlUIParityTestCase


class UIIconParityTestCase(HtmlUIParityTestCase):
    fixture_component = "icon"

    def test_fixture_cases(self):
        fixture = self.load_fixture()
        self.assertGreater(len(fixture["cases"]), 0)
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                self.assert_parity_case(case)
