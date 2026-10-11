"""The renderer declarations that the ``ui-component`` docs directive reads."""

from __future__ import annotations

from alliance_platform.ui.html_components import built_in_registry
from alliance_platform.ui.html_components.base import BaseHtmlUIComponentRenderer
from django.test import SimpleTestCase

from tests.parity.base import HtmlUIParityTestCase


def built_in_renderers() -> dict[str, type[BaseHtmlUIComponentRenderer]]:
    # The registry also holds the test project's example components
    renderers = {}
    for name in built_in_registry.list_names():
        renderer = built_in_registry.get(name)
        assert renderer is not None
        if renderer.__module__.startswith("alliance_platform.ui."):
            renderers[name] = renderer
    return renderers


class RendererDocumentationAttributesTestCase(SimpleTestCase):
    def test_runtime_token_is_set_on_the_components_that_mark_a_runtime(self):
        # button_group, menubar, number_input and text_area call add_auto_attach_marker with it;
        # these are the tokens @alliancesoftware/ui/static-runtime.auto.ts registers
        tokens = {
            name: renderer.runtime_token
            for name, renderer in built_in_renderers().items()
            if renderer.runtime_token is not None
        }

        self.assertEqual(
            tokens,
            {
                "button_group": "smart-orientation",
                "menubar": "menubar",
                "number_input": "number-input",
                "text_area": "text-area",
            },
        )

    def test_documented_props_are_accepted_canonical_names(self):
        for name, renderer in built_in_renderers().items():
            with self.subTest(component=name):
                for prop in renderer.documented_props():
                    self.assertTrue(renderer.supports_prop_name(prop), prop)
                    self.assertEqual(renderer.canonical_prop_name(prop), prop)
                    self.assertFalse(prop.startswith(("data-", "aria-")), prop)

    def test_documented_props_of_a_renderer_with_supported_props(self):
        renderer = built_in_registry.get("button")
        assert renderer is not None

        props = renderer.documented_props()

        self.assertIn("variant", props)
        # A forwarded attribute is accepted too
        self.assertIn("tabIndex", props)
        # A deprecated alias is documented with the prop it names instead
        self.assertNotIn("disabled", props)
        self.assertIn("isDisabled", props)

    def test_documented_props_of_an_input_are_the_names_supports_prop_name_accepts(self):
        renderer = built_in_registry.get("text_input")
        assert renderer is not None
        self.assertIsNone(renderer.supported_props)

        props = renderer.documented_props()

        self.assertTrue({"label", "addonBefore", "maxLength", "labelPosition", "type"} <= props)
        self.assertNotIn("disabled", props)
        self.assertNotIn("renderInput", props)
        self.assertNotIn("aria-describedby", props)

    def test_prop_docs_describe_documented_props(self):
        for name, renderer in built_in_renderers().items():
            open_ended = {
                key
                for key, allowed in (
                    ("data-*", renderer.allow_data_props),
                    ("aria-*", renderer.allow_aria_props),
                )
                if allowed
            }
            with self.subTest(component=name):
                self.assertLessEqual(set(renderer.prop_docs), renderer.documented_props() | open_ended)
                for doc in renderer.prop_docs.values():
                    self.assertTrue(doc.endswith("."), doc)

    def test_prop_docs_describe_the_static_only_props(self):
        expected = {
            "table": {"emptyState", "renderEmptyState", "sortQueryParam"},
            "table_column": {"sortHref"},
            "menubar": {"renderWhenEmpty", "expandedKeysStorageKey"},
            "menubar_item": {"isCurrent", "textValue"},
            "menubar_submenu": {"isCurrent", "textValue", "hideWhenEmpty"},
            "menubar_section": {"hideWhenEmpty"},
            "labeled_input": {"inputId"},
            "number_input": {"minValue", "maxValue"},
        }
        renderers = built_in_renderers()
        for name, props in expected.items():
            with self.subTest(component=name):
                self.assertLessEqual(props, set(renderers[name].prop_docs))


class ApuiMarkerTestCase(HtmlUIParityTestCase):
    def test_has_apui_marker_matches_the_rendered_markup(self):
        table = (
            '{% ui "table" aria_label="Users" %}'
            '{% ui "table_header" %}{% ui "table_column" key="name" %}Name{% endui %}{% endui %}'
            '{% ui "table_body" %}{% ui "table_row" key="1" %}{% ui "table_cell" %}Ann{% endui %}'
            "{% endui %}{% endui %}"
            "{% endui %}"
        )
        menubar = (
            '{% ui "menubar" aria_label="Primary" %}'
            '{% ui "menubar_item" href="/" %}Home{% endui %}'
            '{% ui "menubar_submenu" key="more" title="More" %}'
            '{% ui "menubar_section" title="Account" %}'
            '{% ui "menubar_item" href="/profile/" %}Profile{% endui %}'
            "{% endui %}{% endui %}"
            "{% endui %}"
        )
        templates = {
            "button": '{% ui "button" %}Save{% endui %}',
            "button_group": '{% ui "button_group" %}{% ui "button" %}Save{% endui %}{% endui %}',
            "icon": '{% ui "icon" name="CheckOutlined" %}',
            "text_input": '{% ui "text_input" name="q" %}',
            "number_input": '{% ui "number_input" name="n" %}',
            "text_area": '{% ui "text_area" name="t" %}',
            "labeled_input": (
                '{% ui "labeled_input" label="Colour" input_id="c" %}<select id="c"></select>{% endui %}'
            ),
            "inline_alert": '{% ui "inline_alert" %}Saved{% endui %}',
            "content": '{% ui "content" %}Text{% endui %}',
            "heading": '{% ui "heading" %}Title{% endui %}',
            "header": '{% ui "header" %}Top{% endui %}',
            "footer": '{% ui "footer" %}Bottom{% endui %}',
            "pagination": '{% ui "pagination" total=30 %}',
            **dict.fromkeys(
                ("table", "table_header", "table_body", "table_column", "table_row", "table_cell"), table
            ),
            **dict.fromkeys(("menubar", "menubar_item", "menubar_submenu", "menubar_section"), menubar),
        }
        renderers = built_in_renderers()
        self.assertEqual(set(templates), set(renderers))

        for name, renderer in renderers.items():
            with self.subTest(component=name):
                with self.setup_render_context():
                    output = self.render_ui_template(templates[name])
                self.assertEqual(f'data-apui="{renderer.apui_name}"' in output, renderer.has_apui_marker)
