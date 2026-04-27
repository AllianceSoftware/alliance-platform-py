from __future__ import annotations

from alliance_platform.ui.templatetags.alliance_platform.html_components.components.button import (
    UIButtonRenderer,
)
from alliance_platform.ui.templatetags.alliance_platform.html_components.components.button_group import (
    UIButtonGroupRenderer,
)
from alliance_platform.ui.templatetags.alliance_platform.html_components.registry import (
    HtmlUIComponentRegistry,
)
from django.test import SimpleTestCase


class HtmlUIComponentRegistryTestCase(SimpleTestCase):
    def test_register_and_get(self):
        registry = HtmlUIComponentRegistry()
        registry.register_renderer("button", UIButtonRenderer)

        spec = registry.get("button")
        assert spec is not None
        self.assertEqual(spec.name, "button")
        self.assertIs(spec.renderer_cls, UIButtonRenderer)
        self.assertTrue(registry.exists("button"))

    def test_list_names_preserves_registration_order(self):
        registry = HtmlUIComponentRegistry()
        registry.register_renderer("button", UIButtonRenderer)
        registry.register_renderer("button_group", UIButtonGroupRenderer)

        self.assertEqual(registry.list_names(), ["button", "button_group"])

    def test_registering_same_name_overwrites_renderer(self):
        registry = HtmlUIComponentRegistry()
        registry.register_renderer("button", UIButtonRenderer)
        registry.register_renderer("button", UIButtonGroupRenderer)

        spec = registry.get("button")
        assert spec is not None
        self.assertIs(spec.renderer_cls, UIButtonGroupRenderer)
