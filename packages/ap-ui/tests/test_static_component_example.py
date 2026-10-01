from __future__ import annotations

from alliance_platform.ui.html_components import built_in_registry
from alliance_platform.ui.test_utils import StaticComponentTestCase
from test_alliance_platform_ui.static_components import StatRenderer

from tests.parity.base import test_development_bundler

STYLE_MAPPINGS = {
    "Stat.css.ts": {
        "stat": "stat",
        "label": "stat-label",
        "icon": "stat-icon",
        "value": {"md": "stat-value-md", "lg": "stat-value-lg"},
    },
    "Icon.css.ts": {
        "icon": "icon",
        "variants": {"plain": "icon-plain"},
        "sizes": {"xs": "icon-xs", "sm": "icon-sm", "md": "icon-md"},
    },
}


class StatComponentTestCase(StaticComponentTestCase):
    def render(self, template_body: str) -> str:
        # ap-ui's test bundler resolves the example's stylesheet path without the file existing.
        # In a project, leave out bundler= so the configured bundler resolves your files.
        with self.static_render_context(STYLE_MAPPINGS, bundler=test_development_bundler):
            return self.render_ui_template(template_body)

    def test_renders_label_icon_and_value(self):
        output = self.render(
            '{% ui "stat" label="Open jobs" size="lg" %}'
            '{% ui "icon" name="CheckCircleOutlined" %}{% endui %}'
            '{% ui "stat_value" %}42{% endui %}'
            "{% endui %}"
        )

        self.assertTrue(output.startswith('<div data-apui="stat" data-size="lg" class="stat">'))
        self.assertIn('<span class="stat-label">Open jobs</span>', output)
        # The icon's size and class come from the stat's slot defaults
        self.assertIn('class="icon icon-plain icon-sm stat-icon"', output)
        # The value's class comes from the stat's payload
        self.assertIn('<span data-apui="stat-value" class="stat-value-lg">42</span>', output)
        self.assertNotIn("data-empty", output)

    def test_icon_size_prop_overrides_the_slot_default(self):
        output = self.render(
            '{% ui "stat" label="Open jobs" %}'
            '{% ui "icon" name="CheckCircleOutlined" size="md" %}{% endui %}'
            '{% ui "stat_value" %}42{% endui %}'
            "{% endui %}"
        )

        self.assertIn('class="icon icon-plain icon-md stat-icon"', output)

    def test_payload_reaches_values_nested_in_markup(self):
        output = self.render(
            '{% ui "stat" label="Open jobs" size="lg" %}<p>{% ui "stat_value" %}42{% endui %}</p>{% endui %}'
        )

        self.assertIn('<span data-apui="stat-value" class="stat-value-lg">42</span>', output)
        self.assertNotIn("data-empty", output)

    def test_stat_without_a_rendered_value_is_marked_empty(self):
        output = self.render(
            '{% ui "stat" label="Open jobs" %}{% if False %}{% ui "stat_value" %}42{% endui %}{% endif %}{% endui %}'
        )

        self.assertIn('data-empty="true"', output)

    def test_reports_stop_at_the_nearest_component(self):
        # The payload still reaches the value, but its report goes to the content component, which
        # does not collect reports, so the stat does not see it.
        output = self.render(
            '{% ui "stat" label="Open jobs" %}'
            '{% ui "content" %}{% ui "stat_value" %}42{% endui %}{% endui %}'
            "{% endui %}"
        )

        self.assertIn('class="stat-value-md"', output)
        self.assertIn('data-empty="true"', output)

    def test_value_outside_a_stat_warns_and_renders_nothing(self):
        with self.assertLogs("alliance_platform.ui", level="WARNING") as logs:
            output = self.render('{% ui "stat_value" %}42{% endui %}')

        self.assertEqual(output, "")
        self.assertEqual(
            [record.getMessage() for record in logs.records],
            ["'stat_value' was rendered outside of a 'stat' component; rendering nothing"],
        )

    def test_stylesheet_is_a_bundled_resource(self):
        with self.static_render_context(STYLE_MAPPINGS, bundler=test_development_bundler) as asset_context:
            self.render_ui_template('{% ui "stat" label="Open jobs" %}{% endui %}')
            resource_paths = [str(resource.path) for resource in asset_context.get_resources_for_bundling()]

        self.assertTrue(any(path.endswith("frontend/src/components/Stat.css.ts") for path in resource_paths))

    def test_registered_from_app_config_ready(self):
        self.assertIs(built_in_registry.get("stat"), StatRenderer)
