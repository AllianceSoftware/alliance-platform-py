from __future__ import annotations

from decimal import Decimal
import re
from typing import Any
import warnings

from tests.parity.base import HtmlUIParityTestCase
from tests.parity.normalizers import normalize_html_fragment

_STATIC_EXTENSION_ATTR_RES = [
    re.compile(r'\sdata-apui-attach="number-input"'),
    re.compile(
        r'\sdata-apui-number-input-(?:initial-value|min-value|max-value|step|locale|format-options|value-id)="[^"]*"'
    ),
    re.compile(r'\sid="[^\"]+-value"(?=\sname=)'),
]


def strip_static_number_input_extensions(value: str) -> str:
    normalized = value
    for attr_re in _STATIC_EXTENSION_ATTR_RES:
        normalized = attr_re.sub("", normalized)
    return normalized


class UINumberInputParityTestCase(HtmlUIParityTestCase):
    fixture_component = "number_input"

    def assert_parity_case(self, case: dict[str, Any], context_kwargs: dict[str, Any] | None = None):
        with self.setup_render_context():
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                output = self.render_ui_template(case["template"], context_kwargs)

        actual_html = normalize_html_fragment(strip_static_number_input_extensions(output))
        expected_html = normalize_html_fragment(strip_static_number_input_extensions(case["expected_html"]))
        self.assertEqual(actual_html, expected_html)

        expected_warnings = case.get("expected_warnings", [])
        actual_warnings = [str(item.message) for item in caught_warnings]
        self.assertEqual(actual_warnings, expected_warnings)

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
            "@alliancesoftware/ui/components/number-input/NumberInput.auto.ts",
            "@alliancesoftware/ui/styles/base/focusRing.css.ts",
        ]:
            with self.subTest(resource=expected_suffix):
                self.assertTrue(any(path.endswith(expected_suffix) for path in resource_paths))

    def assert_rendered_values(self, output: str, expected: str):
        self.assertIn(f'data-apui-number-input-initial-value="{expected}"', output)
        self.assertRegex(
            output,
            rf'<input(?=[^>]*type="text")(?=[^>]*value="{re.escape(expected)}")[^>]*/>',
        )
        self.assertRegex(
            output,
            rf'<input(?=[^>]*type="hidden")(?=[^>]*name="quantity")'
            rf'(?=[^>]*value="{re.escape(expected)}")[^>]*/>',
        )

    def render_number_input_value(self, value: Any) -> str:
        with self.setup_render_context():
            return self.render_ui_template(
                '{% ui "number_input" label="Quantity" name="quantity" default_value=value %}{% endui %}',
                {"value": value},
            )

    def test_nan_initial_values_render_as_empty(self):
        for value in (float("nan"), Decimal("NaN")):
            with self.subTest(value_type=type(value).__name__):
                output = self.render_number_input_value(value)

                self.assert_rendered_values(output, "")
                self.assertNotRegex(output, r'(?i)(?:value|initial-value)="nan"')

    def test_finite_numeric_initial_values_are_preserved(self):
        for value, expected in (
            (0, "0"),
            (0.0, "0"),
            (12.5, "12.5"),
            (Decimal("12.50"), "12.50"),
        ):
            with self.subTest(value=value):
                output = self.render_number_input_value(value)

                self.assert_rendered_values(output, expected)
