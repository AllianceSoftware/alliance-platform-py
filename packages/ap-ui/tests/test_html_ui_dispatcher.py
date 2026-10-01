from __future__ import annotations

from alliance_platform.frontend.bundler.context import BundlerAssetContext
from alliance_platform.ui.html_components.diagnostics import StaticComponentContractError
from django.template import Template
from django.template import TemplateSyntaxError
from django.test import override_settings

from tests.parity.base import HtmlUIParityTestCase
from tests.parity.base import test_development_bundler
from tests.test_utils import override_ap_frontend_settings
from tests.test_utils import override_ap_ui_settings
from tests.test_utils.bundler import bypass_frontend_resource_registry


class UIDispatcherTemplateTagTestCase(HtmlUIParityTestCase):
    def test_requires_first_positional_component_selector(self):
        with self.assertRaisesMessage(TemplateSyntaxError, "requires a component selector"):
            Template("{% load alliance_platform.ui %}{% ui %}{% endui %}")

    def test_rejects_extra_positional_args(self):
        with self.assertRaisesMessage(TemplateSyntaxError, "accepts exactly one positional argument"):
            Template('{% load alliance_platform.ui %}{% ui "button" "other" %}{% endui %}')

    def test_dynamic_selector_requires_allowed_components(self):
        with self.assertRaisesMessage(TemplateSyntaxError, "requires allowed_components"):
            Template("{% load alliance_platform.ui %}{% ui component_name %}{% endui %}")

    def test_allowed_components_must_be_literal_string(self):
        with self.assertRaisesMessage(TemplateSyntaxError, "expects allowed_components as a static string"):
            Template(
                "{% load alliance_platform.ui %}{% ui component_name allowed_components=allowed %}{% endui %}"
            )

    def test_allowed_components_entries_must_exist_in_registry(self):
        with self.assertRaisesMessage(TemplateSyntaxError, "invalid allowed_components entries"):
            Template(
                '{% load alliance_platform.ui %}{% ui component_name allowed_components="button,unknown" %}{% endui %}'
            )

    @override_settings(DEBUG=True)
    def test_unknown_static_component_is_error_in_debug(self):
        with self.assertRaisesMessage(TemplateSyntaxError, "Unknown ui component 'missing'"):
            Template('{% load alliance_platform.ui %}{% ui "missing" %}{% endui %}')

    @override_settings(DEBUG=False)
    def test_unknown_static_component_is_error_outside_debug(self):
        with self.assertRaisesMessage(TemplateSyntaxError, "Unknown ui component 'missing'"):
            Template('{% load alliance_platform.ui %}{% ui "missing" %}X{% endui %}')

    def test_dynamic_component_value_not_in_allowed_components_warns_and_renders_empty(self):
        with self.setup_render_context():
            with self.assertLogs("alliance_platform.ui", level="WARNING") as logs:
                output = self.render_ui_template(
                    '{% ui component_name allowed_components="button" %}X{% endui %}',
                    {"component_name": "button_group"},
                )

        self.assertEqual(output, "")
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            ["Resolved ui component 'button_group' is not allowed by allowed_components."],
        )

    @override_ap_ui_settings(STATIC_COMPONENT_STRICT=True)
    def test_dynamic_component_value_not_in_allowed_components_raises_when_strict(self):
        with self.setup_render_context():
            with self.assertRaisesMessage(
                StaticComponentContractError,
                "Resolved ui component 'button_group' is not allowed by allowed_components. "
                "(component 'button_group')",
            ):
                self.render_ui_template(
                    '{% ui component_name allowed_components="button" %}X{% endui %}',
                    {"component_name": "button_group"},
                )

    def test_as_var_sets_context_and_returns_empty_inline_output(self):
        with self.setup_render_context():
            output = self.render_ui_template('{% ui "button" as rendered %}Save{% endui %}{{ rendered }}')

        self.assertIn("<button", output)
        self.assertIn("Save", output)

    def test_dynamic_dispatch_resource_union_uses_allowed_components_order(self):
        with self.setup_render_context() as asset_context:
            self.render_ui_template(
                '{% ui component_name allowed_components=" button, button_group, button " %}Save{% endui %}',
                {"component_name": "button"},
            )
            resource_paths = [str(resource.path) for resource in asset_context.get_resources_for_bundling()]

        expected_suffixes = [
            "@alliancesoftware/ui/components/button/Button.css.ts",
            "@alliancesoftware/ui/styles/base/focusRing.css.ts",
            "@alliancesoftware/ui/components/button/ButtonGroup.css.ts",
            "@alliancesoftware/ui/components/layout/SmartOrientation.css.ts",
            "@alliancesoftware/ui/components/layout/SmartOrientation.auto.ts",
        ]

        indices = []
        for suffix in expected_suffixes:
            index = next((i for i, path in enumerate(resource_paths) if path.endswith(suffix)), -1)
            self.assertNotEqual(index, -1, msg=f"Could not find expected resource suffix: {suffix}")
            indices.append(index)
        self.assertEqual(indices, sorted(indices))

    def test_resource_introspection_does_not_require_active_context(self):
        with override_ap_frontend_settings(BUNDLER=test_development_bundler):
            with BundlerAssetContext(
                frontend_resource_registry=bypass_frontend_resource_registry,
                skip_checks=False,
            ):
                Template("{% load alliance_platform.ui %}{% ui 'button' %}{% endui %}")

    def test_class_alias_merges_with_class_name(self):
        with self.setup_render_context():
            output = self.render_ui_template(
                '{% ui "button" class="alias-class" className="named-class" %}Save{% endui %}'
            )

        self.assertIn("alias-class", output)
        self.assertIn("named-class", output)
        self.assertIn(
            'class="focusRing_base Button_baseButton Button_sizes_md alias-class named-class"', output
        )
