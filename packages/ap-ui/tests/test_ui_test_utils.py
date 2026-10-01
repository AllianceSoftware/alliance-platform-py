from __future__ import annotations

from alliance_platform.frontend.bundler import get_bundler
from alliance_platform.frontend.bundler.context import BundlerAssetContext
from alliance_platform.ui.test_utils import StaticComponentTestCase

from tests.parity.base import test_development_bundler


class StaticComponentTestCaseTestCase(StaticComponentTestCase):
    def test_renders_with_supplied_class_names(self):
        style_mappings = {
            "Button.css.ts": {"baseButton": "button", "sizes": {"md": "button-md"}},
            "focusRing.css.ts": {"base": "focus-ring"},
        }
        with self.static_render_context(style_mappings, bundler=test_development_bundler):
            output = self.render_ui_template('{% ui "button" %}Save{% endui %}')

        self.assertInHTML(
            '<button class="focus-ring button button-md" data-apui="button" data-variant="solid" '
            'data-color="primary" data-size="md" data-shape="default"><span>Save</span></button>',
            output,
        )

    def test_missing_styles_resolve_to_empty_class_names(self):
        with self.static_render_context(
            {"Button.css.ts": {"baseButton": "button"}}, bundler=test_development_bundler
        ):
            output = self.render_ui_template('{% ui "button" class_name="extra" %}Save{% endui %}')

        self.assertIn('class="button extra"', output)

    def test_longest_matching_stylesheet_key_wins(self):
        style_mappings = {
            "Button.css.ts": {"baseButton": "by-name"},
            "components/button/Button.css.ts": {"baseButton": "by-path"},
        }
        with self.static_render_context(style_mappings, bundler=test_development_bundler):
            output = self.render_ui_template('{% ui "button" %}Save{% endui %}')

        self.assertIn('class="by-path"', output)

    def test_yields_the_asset_context(self):
        with self.static_render_context(bundler=test_development_bundler) as asset_context:
            self.assertIs(BundlerAssetContext.get_current(), asset_context)
            self.render_ui_template('{% ui "icon" name="CheckOutlined" %}{% endui %}')
            resource_paths = [str(resource.path) for resource in asset_context.get_resources_for_bundling()]

        self.assertTrue(any(path.endswith("Icon.css.ts") for path in resource_paths))
        self.assertTrue(any(path.endswith("CheckOutlined.svg") for path in resource_paths))

    def test_bundler_defaults_to_the_configured_bundler(self):
        configured_bundler = get_bundler()
        with self.static_render_context():
            self.assertIs(get_bundler(), configured_bundler)
        with self.static_render_context(bundler=test_development_bundler):
            self.assertIs(get_bundler(), test_development_bundler)
        self.assertIs(get_bundler(), configured_bundler)
