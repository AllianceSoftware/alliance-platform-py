from __future__ import annotations

from unittest import mock

from alliance_platform.ui.html_components import register_component
from alliance_platform.ui.html_components.base import BaseHtmlUIComponentRenderer
from alliance_platform.ui.html_components.components.button import UIButtonRenderer
from alliance_platform.ui.html_components.components.button_group import UIButtonGroupRenderer
from alliance_platform.ui.html_components.components.input import UINumberInputRenderer
from alliance_platform.ui.html_components.components.input import UITextAreaRenderer
from alliance_platform.ui.html_components.components.input import UITextInputRenderer
from alliance_platform.ui.html_components.components.layout import UIContentRenderer
from alliance_platform.ui.html_components.components.layout import UIFooterRenderer
from alliance_platform.ui.html_components.components.layout import UIHeaderRenderer
from alliance_platform.ui.html_components.components.layout import UIHeadingRenderer
from alliance_platform.ui.html_components.components.pagination import UIPaginationRenderer
from alliance_platform.ui.html_components.registry import HtmlUIComponentRegistry
from alliance_platform.ui.html_components.registry import built_in_registry
from django.template import Template
from django.template import TemplateSyntaxError
from django.test import SimpleTestCase

from tests.parity.base import HtmlUIParityTestCase


class AlternateButtonRenderer(UIButtonRenderer):
    """Inherits ``name = "button"`` so it can replace the built-in button."""


class RenamedButtonRenderer(UIButtonRenderer):
    name = "submit_button"


class MarkedButtonRenderer(UIButtonRenderer):
    name = "marked_button"
    apui_name = "button"


def get_renderer_types(template_obj: Template) -> list[type]:
    return [type(node) for node in template_obj.nodelist.get_nodes_by_type(BaseHtmlUIComponentRenderer)]


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

    def test_registering_a_different_renderer_under_a_taken_name_raises(self):
        registry = HtmlUIComponentRegistry()
        registry.register_renderer("button", UIButtonRenderer)

        with self.assertRaisesMessage(ValueError, "'button' is already registered to UIButtonRenderer"):
            registry.register_renderer("button", AlternateButtonRenderer)
        self.assertIs(registry.get("button"), UIButtonRenderer)

    def test_replace_overwrites_renderer(self):
        registry = HtmlUIComponentRegistry()
        registry.register_renderer("button", UIButtonRenderer)
        registry.register_renderer("button", AlternateButtonRenderer, replace=True)

        self.assertIs(registry.get("button"), AlternateButtonRenderer)

    def test_registering_the_same_renderer_again_is_a_no_op(self):
        # AppConfig.ready() can run more than once in tests that change INSTALLED_APPS
        registry = HtmlUIComponentRegistry()
        registry.register_renderer("button", UIButtonRenderer)
        registry.register_renderer("button", UIButtonRenderer)

        self.assertEqual(registry.list_names(), ["button"])

    def test_name_must_be_snake_case(self):
        registry = HtmlUIComponentRegistry()
        for name in ("Button", "button-group", "buttonGroup", "1button", "_button", "button group", ""):
            with self.subTest(name=name):
                with self.assertRaisesMessage(ValueError, "use snake_case"):
                    registry.register_renderer(name, UIButtonRenderer)

    def test_renderer_name_must_match_the_registered_name(self):
        registry = HtmlUIComponentRegistry()
        with self.assertRaisesMessage(ValueError, "its name attribute is 'button'"):
            registry.register_renderer("submit_button", UIButtonRenderer)
        self.assertFalse(registry.exists("submit_button"))

    def test_renderer_must_subclass_the_base_renderer(self):
        registry = HtmlUIComponentRegistry()
        with self.assertRaisesMessage(TypeError, "must subclass BaseHtmlUIComponentRenderer"):
            registry.register_renderer("thing", object)

    def test_apui_name_defaults_to_the_hyphenated_name(self):
        self.assertEqual(UIButtonRenderer.apui_name, "button")
        self.assertEqual(UIButtonGroupRenderer.apui_name, "button-group")
        self.assertEqual(UITextInputRenderer.apui_name, "text-input")
        self.assertEqual(UINumberInputRenderer.apui_name, "number-input")
        # A subclass that keeps the name keeps the marker; a new name derives a new marker unless
        # the class sets apui_name itself
        self.assertEqual(AlternateButtonRenderer.apui_name, "button")
        self.assertEqual(RenamedButtonRenderer.apui_name, "submit-button")
        self.assertEqual(MarkedButtonRenderer.apui_name, "button")

    def test_every_built_in_renderer_name_matches_its_registration(self):
        for name in built_in_registry.list_names():
            with self.subTest(component=name):
                renderer_cls = built_in_registry.get(name)
                assert renderer_cls is not None
                self.assertEqual(renderer_cls.name, name)
                self.assertEqual(renderer_cls.apui_name, name.replace("_", "-"))

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

    def test_built_in_registry_includes_generic_layout_components(self):
        for name, renderer_cls in [
            ("content", UIContentRenderer),
            ("heading", UIHeadingRenderer),
            ("header", UIHeaderRenderer),
            ("footer", UIFooterRenderer),
        ]:
            with self.subTest(component=name):
                self.assertIs(built_in_registry.get(name), renderer_cls)


class RegisterComponentTestCase(HtmlUIParityTestCase):
    def setUp(self):
        # Restore the default registry after each test
        patcher = mock.patch.dict(built_in_registry._renderers)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_registered_component_renders_through_the_ui_tag(self):
        register_component("submit_button", RenamedButtonRenderer)

        with self.setup_render_context():
            output = self.render_ui_template('{% ui "submit_button" type="submit" %}Save{% endui %}')

        self.assertIn('data-apui="submit-button"', output)
        self.assertIn('type="submit"', output)
        self.assertIn("<span>Save</span>", output)

    def test_registered_component_is_accepted_by_allowed_components(self):
        register_component("submit_button", RenamedButtonRenderer)

        with self.setup_render_context():
            output = self.render_ui_template(
                '{% ui component allowed_components="button,submit_button" %}Save{% endui %}',
                {"component": "submit_button"},
            )

        self.assertIn('data-apui="submit-button"', output)

    def test_unregistered_names_still_fail_at_compile_time(self):
        with self.setup_render_context():
            with self.assertRaisesMessage(TemplateSyntaxError, "Unknown ui component 'submit_button'"):
                self.render_ui_template('{% ui "submit_button" %}Save{% endui %}')

    def test_register_component_refuses_to_shadow_a_built_in(self):
        with self.assertRaisesMessage(ValueError, "pass replace=True"):
            register_component("button", AlternateButtonRenderer)
        self.assertIs(built_in_registry.get("button"), UIButtonRenderer)

    def test_replacement_applies_to_templates_compiled_afterwards(self):
        template_body = '{% load alliance_platform.ui %}{% ui "button" %}Save{% endui %}'
        with self.setup_render_context():
            compiled_before = Template(template_body)
            register_component("button", AlternateButtonRenderer, replace=True)
            compiled_after = Template(template_body)

        self.assertEqual(get_renderer_types(compiled_before), [UIButtonRenderer])
        self.assertEqual(get_renderer_types(compiled_after), [AlternateButtonRenderer])
