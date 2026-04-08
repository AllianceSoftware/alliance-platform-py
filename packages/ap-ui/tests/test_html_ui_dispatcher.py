from __future__ import annotations

from contextlib import contextmanager
from unittest import mock
import warnings

from alliance_platform.frontend.bundler.context import BundlerAssetContext
from alliance_platform.ui.templatetags.alliance_platform.html_components import dispatcher
from django.template import Context
from django.template import Template
from django.template import TemplateSyntaxError
from django.test import SimpleTestCase
from django.test import override_settings

from tests.parity.style_mocks import make_style_mapping_resolver
from tests.test_utils import override_ap_frontend_settings
from tests.test_utils.bundler import TestViteBundler
from tests.test_utils.bundler import bundler_kwargs
from tests.test_utils.bundler import bypass_frontend_resource_registry

test_development_bundler = TestViteBundler(
    **bundler_kwargs,  # type: ignore[arg-type]
    mode="development",
)


class UIDispatcherTemplateTagTestCase(SimpleTestCase):
    def setUp(self):
        dispatcher._DISPATCHER_WARNING_KEYS.clear()

    @contextmanager
    def setup_render_context(self):
        with override_ap_frontend_settings(BUNDLER=test_development_bundler):
            with BundlerAssetContext(
                skip_checks=True,
                frontend_resource_registry=bypass_frontend_resource_registry,
            ) as asset_context:
                with mock.patch(
                    "alliance_platform.ui.templatetags.alliance_platform.html_components.base.resolve_vanilla_extract_class_mapping",
                    side_effect=make_style_mapping_resolver(),
                ):
                    yield asset_context

    def render_ui_template(self, template_body: str, context_kwargs=None):
        template_obj = Template("{% load alliance_platform.ui %}" + template_body)
        context_obj = Context(context_kwargs or {})
        context_obj.template = template_obj
        return template_obj.render(context_obj)

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
    def test_unknown_static_component_warns_once_and_renders_empty(self):
        with self.setup_render_context():
            template_obj = Template('{% load alliance_platform.ui %}{% ui "missing" %}X{% endui %}')
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                first = template_obj.render(Context())
                second = template_obj.render(Context())

        self.assertEqual(first, "")
        self.assertEqual(second, "")
        self.assertEqual(len(caught), 1)
        self.assertEqual(str(caught[0].message), "Unknown ui component 'missing'")

    def test_dynamic_component_value_not_in_allowed_components_warns_and_renders_empty(self):
        with self.setup_render_context():
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                output = self.render_ui_template(
                    '{% ui component_name allowed_components="button" %}X{% endui %}',
                    {"component_name": "button_group"},
                )

        self.assertEqual(output, "")
        self.assertEqual(len(caught), 1)
        self.assertIn("is not allowed by allowed_components", str(caught[0].message))

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
            "@alliancesoftware/ui/components/layout/SmartOrientation.attach.ts",
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
        self.assertIn('class="focus-ring-base button-base button-size-md alias-class named-class"', output)
