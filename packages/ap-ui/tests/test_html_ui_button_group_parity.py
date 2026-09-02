from __future__ import annotations

from unittest.mock import patch
import warnings

from alliance_platform.ui.templatetags.alliance_platform.html_components.components.button_group import (
    UIButtonGroupRenderer,
)
from django.template import TemplateSyntaxError

from tests.parity.base import HtmlUIParityTestCase
from tests.parity.normalizers import normalize_html_fragment


class UIButtonGroupParityTestCase(HtmlUIParityTestCase):
    fixture_component = "button_group"

    def render_with_warnings(self, template_body: str, context_kwargs=None):
        with self.setup_render_context():
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                output = self.render_ui_template(template_body, context_kwargs)
        return output, [str(item.message) for item in caught_warnings]

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

    def test_shared_rules_normalize_group_and_inherited_button_props(self):
        output, caught = self.render_with_warnings(
            '{% ui "button_group" orientation="diagonal" align="middle" density="dense" '
            'variant="raised" color="green" size="huge" %}'
            '{% ui "button" %}One{% endui %}'
            "{% endui %}"
        )

        self.assertEqual(
            caught,
            [
                "Invalid 'orientation' prop passed: diagonal",
                "Invalid 'align' prop passed: middle",
                "Invalid 'density' prop passed: dense",
                "Invalid 'variant' prop passed: raised",
                "Invalid 'color' prop passed: green",
                "Invalid 'size' prop passed: huge",
            ],
        )
        self.assertIn('data-orientation="horizontal"', output)
        self.assertIn('data-align="start"', output)
        self.assertIn('data-density="md"', output)
        self.assertIn('data-variant="solid"', output)
        self.assertIn('data-color="primary"', output)
        self.assertIn('data-size="md"', output)

    def test_omitted_group_props_do_not_become_explicit_data_or_slot_props(self):
        output, caught = self.render_with_warnings(
            '{% ui "button_group" %}{% ui "button" variant="plain" %}One{% endui %}{% endui %}'
        )

        self.assertEqual(caught, [])
        self.assertNotIn("data-density", output)
        self.assertNotIn("data-align", output)
        self.assertIn('data-variant="plain"', output)

    def test_group_forwards_static_div_props_and_drops_unknown_and_event_props(self):
        output, caught = self.render_with_warnings(
            '{% ui "button_group" title="Actions" data_testid="actions" aria_label="Actions" '
            'unknown_prop="nope" on_click="alert(1)" %}'
            '{% ui "button" %}One{% endui %}'
            "{% endui %}"
        )

        self.assertEqual(
            caught,
            [
                "Prop 'unknownProp' is not a supported 'button-group' prop and will be ignored",
                "Prop 'onClick' will be ignored: event handlers are not supported by static button-group components",
            ],
        )
        self.assertIn('title="Actions"', output)
        self.assertIn('data-testid="actions"', output)
        self.assertIn('aria-label="Actions"', output)
        self.assertNotIn("nope", output)
        self.assertNotIn("alert", output)

    def test_missing_smart_orientation_runtime_is_an_upgrade_error(self):
        original = UIButtonGroupRenderer.resolve_frontend_resource

        def resolve_frontend_resource(renderer, path, resolve_extensions=None):
            if path.endswith("SmartOrientation.auto.ts"):
                raise TemplateSyntaxError("missing runtime")
            return original(renderer, path, resolve_extensions)

        with self.setup_render_context():
            with self.assertRaisesMessage(
                TemplateSyntaxError,
                "Upgrade @alliancesoftware/ui to a compatible version",
            ):
                with patch.object(
                    UIButtonGroupRenderer,
                    "resolve_frontend_resource",
                    resolve_frontend_resource,
                ):
                    self.render_ui_template(
                        '{% ui "button_group" %}{% ui "button" %}One{% endui %}{% endui %}'
                    )
