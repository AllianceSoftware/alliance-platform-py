from alliance_platform.frontend.bundler.context import BundlerAssetContext
from alliance_platform.frontend.templatetags.react import CommonComponentSource
from alliance_platform.frontend.templatetags.react import ComponentNode
from alliance_platform.frontend.util import transform_attribute_names
from django.template import Context
from django.template import Origin
from django.test import SimpleTestCase

from tests.test_utils.bundler import bypass_frontend_asset_registry


class TestTransformAttributeNames(SimpleTestCase):
    def test_style_string_is_converted_to_style_object(self):
        attrs = transform_attribute_names({"style": "margin-right: 5px; color: red;"})
        self.assertEqual(
            attrs,
            {
                "style": {
                    "marginRight": "5px",
                    "color": "red",
                }
            },
        )

    def test_style_parser_handles_semicolons_inside_values(self):
        attrs = transform_attribute_names(
            {"style": 'background-image: url("data:image/svg+xml;base64,abc;def"); margin-right: 5px'}
        )
        self.assertEqual(
            attrs["style"],
            {
                "backgroundImage": 'url("data:image/svg+xml;base64,abc;def")',
                "marginRight": "5px",
            },
        )

    def test_style_parser_handles_custom_properties_and_vendor_prefixes(self):
        attrs = transform_attribute_names(
            {"style": "-webkit-line-clamp: 2; -ms-transition: all 1s; --custom-color: red;"}
        )
        self.assertEqual(
            attrs["style"],
            {
                "WebkitLineClamp": "2",
                "msTransition": "all 1s",
                "--custom-color": "red",
            },
        )

    def test_style_parser_preserves_values_as_plain_strings(self):
        attrs = transform_attribute_names(
            {"style": "background-image: url('</script><script>alert(1)</script>')"}
        )
        self.assertEqual(
            attrs["style"],
            {
                "backgroundImage": "url('</script><script>alert(1)</script>')",
            },
        )

    def test_style_parser_ignores_invalid_declarations(self):
        attrs = transform_attribute_names({"style": "margin-right 5px; color: red; : bad; font-size: 12px"})
        self.assertEqual(
            attrs["style"],
            {
                "color": "red",
                "fontSize": "12px",
            },
        )

    def test_style_parser_returns_empty_for_garbage(self):
        attrs = transform_attribute_names({"style": ";;;; not-a-declaration"})
        self.assertEqual(attrs["style"], {})

    def test_style_parser_ignores_unmatched_quotes(self):
        attrs = transform_attribute_names({"style": "color: 'red; font-size: 12px"})
        self.assertEqual(attrs["style"], {})

    def test_style_parser_ignores_trailing_colon(self):
        attrs = transform_attribute_names({"style": "color: red; width:"})
        self.assertEqual(attrs["style"], {"color": "red", "width": ""})

    def test_style_parser_handles_only_custom_properties(self):
        attrs = transform_attribute_names({"style": "--primary-color: blue; --spacing: 4px;"})
        self.assertEqual(attrs["style"], {"--primary-color": "blue", "--spacing": "4px"})

    def test_component_node_converts_style_prop_string(self):
        with BundlerAssetContext(frontend_asset_registry=bypass_frontend_asset_registry, skip_checks=True):
            node = ComponentNode(
                Origin("test"),
                CommonComponentSource("div"),
                {"style": "margin-right: 5px"},
            )
            props = node.resolve_props(Context())
            self.assertEqual(props.props["style"], {"marginRight": "5px"})
