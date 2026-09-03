from __future__ import annotations

from alliance_platform.ui.templatetags.alliance_platform.html_components.components.button import (
    UIButtonRenderer,
)
from alliance_platform.ui.templatetags.alliance_platform.html_components.components.button_group import (
    UIButtonGroupRenderer,
)
from alliance_platform.ui.templatetags.alliance_platform.html_components.components.input import (
    UINumberInputRenderer,
)
from alliance_platform.ui.templatetags.alliance_platform.html_components.components.input import (
    UITextAreaRenderer,
)
from alliance_platform.ui.templatetags.alliance_platform.html_components.components.input import (
    UITextInputRenderer,
)
from alliance_platform.ui.templatetags.alliance_platform.html_components.components.pagination import (
    UIPaginationRenderer,
)
from alliance_platform.ui.templatetags.alliance_platform.html_components.registry import (
    HtmlUIComponentRegistry,
)
from alliance_platform.ui.templatetags.alliance_platform.html_components.registry import built_in_registry
from django.test import SimpleTestCase


class HtmlUIComponentRegistryTestCase(SimpleTestCase):
    def test_register_and_get(self):
        registry = HtmlUIComponentRegistry()
        registry.register_renderer("button", UIButtonRenderer)

        renderer_cls = registry.get("button")
        self.assertIs(renderer_cls, UIButtonRenderer)
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

        renderer_cls = registry.get("button")
        self.assertIs(renderer_cls, UIButtonGroupRenderer)

    def test_built_in_registry_includes_input_components(self):
        for name, renderer_cls in [
            ("text_input", UITextInputRenderer),
            ("number_input", UINumberInputRenderer),
            ("text_area", UITextAreaRenderer),
        ]:
            with self.subTest(component=name):
                self.assertIs(built_in_registry.get(name), renderer_cls)

    def test_built_in_registry_includes_pagination(self):
        self.assertIs(built_in_registry.get("pagination"), UIPaginationRenderer)
