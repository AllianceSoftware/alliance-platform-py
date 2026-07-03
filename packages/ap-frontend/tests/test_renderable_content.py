from alliance_platform.frontend.bundler.context import BundlerAssetContext
from alliance_platform.frontend.html_parser import convert_html_string
from alliance_platform.frontend.renderable_content import RenderableContent
from alliance_platform.frontend.renderable_content import RenderableElement
from alliance_platform.frontend.renderable_content import RenderableText
from alliance_platform.frontend.renderable_content import is_renderable_content
from alliance_platform.frontend.templatetags.react import CommonComponentSource
from alliance_platform.frontend.templatetags.react import ComponentNode
from django.template import Origin
from django.test import SimpleTestCase

from .test_utils import override_ap_frontend_settings
from .test_utils.bundler import TestViteBundler
from .test_utils.bundler import bundler_kwargs
from .test_utils.bundler import bypass_frontend_resource_registry

origin = Origin("UNKNOWN")

test_development_bundler = TestViteBundler(
    **bundler_kwargs,  # type: ignore[arg-type]
    mode="development",
)


@override_ap_frontend_settings(BUNDLER=test_development_bundler)
class RenderableContentTestCase(SimpleTestCase):
    def setUp(self):
        # Building ComponentNodes (convert_html_string) requires an active BundlerAssetContext
        self.bundler_context = BundlerAssetContext(
            frontend_resource_registry=bypass_frontend_resource_registry, skip_checks=True
        )
        self.bundler_context.__enter__()
        self.addCleanup(self.bundler_context.__exit__, None, None, None)

    def test_from_html_single_element(self):
        content = RenderableContent.from_html("<span>Help</span>", origin)
        self.assertFalse(content.is_empty())
        self.assertEqual(len(content.parts), 1)
        element = content.parts[0]
        assert isinstance(element, RenderableElement)
        self.assertEqual(element.tag, "span")
        self.assertEqual(dict(element.attrs), {})
        self.assertEqual(element.children.parts, (RenderableText("Help"),))

    def test_from_html_keeps_html_attribute_names(self):
        content = RenderableContent.from_html('<label for="email" class="hint">Email</label>', origin)
        element = content.parts[0]
        assert isinstance(element, RenderableElement)
        self.assertEqual(dict(element.attrs), {"for": "email", "class": "hint"})

    def test_from_html_mixed_content_preserves_order(self):
        content = RenderableContent.from_html("Use <strong>bold</strong> text", origin)
        self.assertEqual(len(content.parts), 3)
        first, middle, last = content.parts
        self.assertEqual(first, RenderableText("Use "))
        assert isinstance(middle, RenderableElement)
        self.assertEqual(middle.tag, "strong")
        self.assertEqual(last, RenderableText(" text"))

    def test_from_html_invalid_html_returns_empty(self):
        content = RenderableContent.from_html("</p>", origin)
        self.assertTrue(content.is_empty())

    def test_from_text_does_not_parse_html(self):
        content = RenderableContent.from_text("<span>not parsed</span>")
        self.assertEqual(content.parts, (RenderableText("<span>not parsed</span>"),))

    def test_from_text_empty(self):
        self.assertTrue(RenderableContent.from_text("").is_empty())
        self.assertTrue(RenderableContent.from_text(None).is_empty())

    def test_is_renderable_content(self):
        self.assertTrue(is_renderable_content(RenderableContent.from_text("x")))
        self.assertFalse(is_renderable_content("x"))

    def test_as_plain_text_returns_text_for_text_only_content(self):
        self.assertEqual(
            RenderableContent.from_html("No markup here", origin).as_plain_text(), "No markup here"
        )
        # character references resolve to their unicode value like any parsed text
        self.assertEqual(RenderableContent.from_html("a &amp; b", origin).as_plain_text(), "a & b")
        self.assertEqual(RenderableContent.from_text("plain").as_plain_text(), "plain")

    def test_as_plain_text_returns_none_for_rich_or_empty_content(self):
        self.assertIsNone(RenderableContent.from_html("<span>Help</span>", origin).as_plain_text())
        self.assertIsNone(
            RenderableContent.from_html("Use <strong>bold</strong> text", origin).as_plain_text()
        )
        self.assertIsNone(RenderableContent(()).as_plain_text())

    def test_convert_html_string_still_returns_component_nodes(self):
        nodes = convert_html_string("<span>Help</span>", origin)
        self.assertEqual(len(nodes), 1)
        node = nodes[0]
        assert isinstance(node, ComponentNode)
        self.assertEqual(node.source, CommonComponentSource("span"))
        self.assertEqual(list(node.props["children"]), ["Help"])

    def test_convert_html_string_applies_react_attribute_names(self):
        nodes = convert_html_string('<label for="email" class="hint">Email</label>', origin)
        node = nodes[0]
        assert isinstance(node, ComponentNode)
        self.assertEqual(node.props["htmlFor"], "email")
        self.assertEqual(node.props["className"], "hint")

    def test_convert_html_string_applies_element_specific_mappings(self):
        nodes = convert_html_string('<input value="abc">', origin)
        node = nodes[0]
        assert isinstance(node, ComponentNode)
        self.assertEqual(node.props["defaultValue"], "abc")

    def test_convert_html_string_mixed_content(self):
        nodes = convert_html_string("Use <strong>bold</strong> text", origin)
        self.assertEqual(nodes[0], "Use ")
        assert isinstance(nodes[1], ComponentNode)
        self.assertEqual(nodes[1].source, CommonComponentSource("strong"))
        self.assertEqual(nodes[2], " text")

    def test_invalid_attribute_names_warn_and_are_dropped(self):
        with self.assertWarnsRegex(UserWarning, "The following parts were removed from tag"):
            content = RenderableContent.from_html('<span bad"name="x" ok="1">Help</span>', origin)
        element = content.parts[0]
        assert isinstance(element, RenderableElement)
        self.assertEqual(dict(element.attrs), {"ok": "1"})
