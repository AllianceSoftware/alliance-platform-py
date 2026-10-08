from __future__ import annotations

from decimal import Decimal
import re
from typing import Any

from tests.parity.base import HtmlUIParityTestCase

_STATIC_EXTENSION_ATTR_RES = [
    re.compile(r'\sdata-apui-attach="number-input"'),
    re.compile(
        r'\sdata-apui-number-input-(?:initial-value|min-value|max-value|step|locale|format-options)="[^"]*"'
    ),
]
_VISIBLE_INPUT_RE = re.compile(r'<input\b(?=[^>]*\stype="text")[^>]*>')
_NAME_ATTR_RE = re.compile(r'\sname="[^"]*"')


def strip_static_number_input_extensions(value: str) -> str:
    normalized = value
    for attr_re in _STATIC_EXTENSION_ATTR_RES:
        normalized = attr_re.sub("", normalized)
    return normalized


def strip_static_visible_input_name(value: str) -> str:
    """Drop ``name`` from the static visible input.

    The static visible input keeps the field name so it submits without JavaScript. React (and the
    attach runtime) submit through a separate hidden input instead, which the fixture generator
    removes from the React output.
    """
    return _VISIBLE_INPUT_RE.sub(lambda match: _NAME_ATTR_RE.sub("", match.group(0)), value)


class UINumberInputParityTestCase(HtmlUIParityTestCase):
    fixture_component = "number_input"

    def normalize_static_html(self, html: str, fixture: dict[str, Any]) -> str:
        return strip_static_visible_input_name(
            strip_static_number_input_extensions(super().normalize_static_html(html, fixture))
        )

    def normalize_expected_html(self, html: str) -> str:
        return strip_static_number_input_extensions(html)

    def test_fixture_cases(self):
        fixture = self.load_fixture()
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                self.assert_parity_case(case)

    def test_resources_are_registered(self):
        with self.setup_render_context() as asset_context:
            self.render_ui_template('{% ui "number_input" label="Quantity" %}')
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
        # The visible input submits the value natively; the attach runtime creates any hidden input
        self.assertRegex(
            output,
            rf'<input(?=[^>]*type="text")(?=[^>]*name="quantity")'
            rf'(?=[^>]*value="{re.escape(expected)}")[^>]*/>',
        )
        self.assertNotIn('type="hidden"', output)

    def render_number_input_value(self, value: Any) -> str:
        with self.setup_render_context():
            return self.render_ui_template(
                '{% ui "number_input" label="Quantity" name="quantity" default_value=value %}',
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
