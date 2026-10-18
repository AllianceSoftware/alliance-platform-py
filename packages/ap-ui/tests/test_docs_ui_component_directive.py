"""The ``ui-component`` docs directive's reference data, and the renderer declarations it reads."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
from typing import Any

from alliance_platform.ui.html_components import base
from alliance_platform.ui.html_components import built_in_registry
from alliance_platform.ui.html_components.base import BaseHtmlUIComponentRenderer
from alliance_platform.ui.html_components.components import UIButtonRenderer
from alliance_platform.ui.html_components.components import UIIconRenderer
from alliance_platform.ui.html_components.components import UIMenubarRenderer
from alliance_platform.ui.html_components.components import UITableColumnRenderer
from alliance_platform.ui.html_components.components import UITextAreaRenderer
from alliance_platform.ui.html_components.components import UITextInputRenderer
from alliance_platform.ui.html_components.registry import HtmlUIComponentRegistry
from django.test import SimpleTestCase
from test_alliance_platform_ui.static_components import StatRenderer

from tests.parity.base import HtmlUIParityTestCase

# The directive's modules live in the repository's docs utilities, which docs/conf.py puts on
# sys.path; ap_ui_component_reference imports neither Sphinx nor docutils
_DOC_UTILS_DIR = Path(__file__).resolve().parents[3] / "docs" / "_doc_utils"
if str(_DOC_UTILS_DIR) not in sys.path:
    sys.path.append(str(_DOC_UTILS_DIR))
reference_module: Any = importlib.import_module("ap_ui_component_reference")
describe_component = reference_module.describe_component
component_reference_rst = reference_module.component_reference_rst
load_registry = reference_module.load_registry
template_prop_name = reference_module.template_prop_name

STORYBOOK = "https://ui.alliance.software/?path=/docs/"


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
            "checkbox": '{% ui "checkbox" %}Accept{% endui %}',
            "checkbox_group": (
                '{% ui "checkbox_group" label="Pets" %}{% ui "checkbox" value="cat" %}Cat{% endui %}{% endui %}'
            ),
            **dict.fromkeys(
                ("radio_group", "radio"),
                '{% ui "radio_group" label="Colour" %}{% ui "radio" value="red" %}Red{% endui %}{% endui %}',
            ),
            "native_select": '{% ui "native_select" name="c" %}<option>Red</option>{% endui %}',
        }
        renderers = built_in_renderers()
        self.assertEqual(set(templates), set(renderers))

        for name, renderer in renderers.items():
            with self.subTest(component=name):
                with self.setup_render_context():
                    output = self.render_ui_template(templates[name])
                self.assertEqual(f'data-apui="{renderer.apui_name}"' in output, renderer.has_apui_marker)


class DescribeComponentTestCase(SimpleTestCase):
    def props(self, reference) -> dict[str, Any]:
        return {prop.name: prop for prop in reference.props}

    def test_leaf_component(self):
        reference = describe_component("icon")

        self.assertFalse(reference.has_children)
        self.assertEqual(reference.usage, '{% ui "icon" %}')
        self.assertIsNone(reference.apui_marker)
        self.assertEqual(reference.slot_name, "icon")
        self.assertIsNone(reference.parent)
        self.assertIsNone(reference.runtime_token)
        self.assertEqual(reference.react_tag, "Icon")
        self.assertEqual(reference.react_docs_url, f"{STORYBOOK}icons-icons--docs")
        self.assertEqual(
            [prop.template_name for prop in reference.props],
            ["class", "color", "name", "size", "slot", "variant"],
        )
        self.assertEqual(self.props(reference)["name"].doc, UIIconRenderer.prop_docs["name"])
        self.assertEqual(reference.forwarded_attributes, ("id", "style", "title"))

    def test_container_component(self):
        reference = describe_component("button")
        props = self.props(reference)

        self.assertTrue(reference.has_children)
        self.assertEqual(reference.usage, '{% ui "button" %}...{% endui %}')
        self.assertEqual(reference.apui_marker, "button")
        self.assertEqual(reference.slot_name, "button")
        self.assertEqual(reference.react_docs_url, f"{STORYBOOK}ui-button--docs")
        # The tag's content is not a prop, and forwarded attributes are listed apart
        self.assertNotIn("children", props)
        self.assertNotIn("tabIndex", props)
        self.assertIn("tab_index", reference.forwarded_attributes)
        self.assertTrue(reference.allows_data_attributes)
        self.assertTrue(reference.allows_aria_attributes)

        variant = props["variant"]
        self.assertEqual(
            variant.values, ('``"solid"``', '``"outlined"``', '``"plain"``', '``"light"``', '``"link"``')
        )
        self.assertEqual(variant.invalid_fallback, '``"solid"``')
        self.assertIsNone(variant.doc)
        is_disabled = props["isDisabled"]
        self.assertEqual(is_disabled.template_name, "is_disabled")
        self.assertEqual(is_disabled.deprecated_aliases, ("disabled",))
        self.assertEqual(is_disabled.values, ())
        self.assertIsNone(is_disabled.invalid_fallback)
        # A rule without a fallback drops an invalid value
        self.assertEqual(props["elementType"].values, ("``str``",))
        self.assertEqual(props["elementType"].invalid_fallback, "omitted")

        self.assertEqual(reference.unsupported_props, ())
        self.assertEqual(
            reference.event_handler_reason, "event handlers are not supported by static button components"
        )
        # The directive rebuilds the page when these change
        self.assertIn(base.__file__, reference.source_files)
        self.assertIn(sys.modules[UIButtonRenderer.__module__].__file__, reference.source_files)

    def test_input_lists_the_props_supports_prop_name_accepts(self):
        reference = describe_component("text_input")
        props = self.props(reference)

        self.assertTrue({"label", "addonBefore", "maxLength", "readOnly", "inputSize", "type"} <= set(props))
        self.assertNotIn("disabled", props)
        self.assertEqual(reference.apui_marker, "text-input")
        self.assertTrue(props["addonBefore"].rich_content)
        self.assertFalse(props["label"].rich_content)
        self.assertEqual(props["inputSize"].values, ('``"sm"``', '``"md"``'))
        self.assertEqual(props["id"].doc, UITextInputRenderer.prop_docs["id"])
        self.assertEqual(len(reference.unsupported_props), 1)
        refused = reference.unsupported_props[0]
        self.assertIn("render_input", refused.template_names)
        self.assertIn("input_props", refused.template_names)
        self.assertEqual(refused.reason, "React-only props are not supported by static input components")

    def test_part_with_a_parent_requirement(self):
        reference = describe_component("table_column")
        props = self.props(reference)

        self.assertEqual(reference.parent, "table")
        self.assertIsNone(reference.apui_marker)
        self.assertEqual(reference.react_tag, "Column")
        self.assertEqual(reference.react_docs_url, f"{STORYBOOK}ui-table--docs")
        self.assertEqual(props["sortHref"].doc, UITableColumnRenderer.prop_docs["sortHref"])
        self.assertEqual(props["sortDirection"].values, ('``"ascending"``', '``"descending"``'))
        self.assertEqual(reference.forwarded_attributes, ())
        self.assertFalse(reference.allows_data_attributes)
        self.assertEqual(describe_component("menubar_item").parent, "menubar")
        self.assertIsNone(describe_component("table").parent)
        self.assertEqual(describe_component("table_header").props, ())
        radio = describe_component("radio")
        self.assertEqual(radio.parent, "radio_group")
        self.assertEqual(radio.apui_marker, "radio")
        self.assertEqual(radio.react_docs_url, f"{STORYBOOK}ui-radiogroup--docs")
        # A checkbox renders inside a checkbox group or on its own
        self.assertIsNone(describe_component("checkbox").parent)

    def test_runtime_token_prop_docs_and_unsupported_props(self):
        reference = describe_component("menubar")
        props = self.props(reference)

        self.assertEqual(reference.runtime_token, "menubar")
        self.assertEqual(reference.apui_marker, "menubar")
        self.assertEqual(
            props["expandedKeysStorageKey"].doc, UIMenubarRenderer.prop_docs["expandedKeysStorageKey"]
        )
        self.assertTrue(props["defaultExpandedKeys"].non_scalar)
        self.assertTrue(reference.allows_data_attributes)
        self.assertFalse(reference.allows_aria_attributes)
        self.assertEqual(
            reference.extra_aria_attributes, ("aria_describedby", "aria_label", "aria_labelledby")
        )
        groups = {group.template_names: group.reason for group in reference.unsupported_props}
        self.assertEqual(
            groups[
                (
                    "default_selected_keys",
                    "on_selection_change",
                    "selected_keys",
                    "selection_behavior",
                    "selection_mode",
                )
            ],
            "selection is not supported by static menubar components",
        )
        self.assertIn(("disabled_keys",), groups)
        # Grouped props and groups are sorted, so the output does not depend on set order
        self.assertEqual(list(groups), sorted(groups))

    def test_aliases_and_open_ended_attribute_docs(self):
        item = self.props(describe_component("menubar_item"))
        self.assertEqual(item["isCurrent"].aliases, ("current",))
        self.assertEqual(item["isCurrent"].deprecated_aliases, ())
        self.assertEqual(self.props(describe_component("number_input"))["minValue"].aliases, ("min",))

        labeled_input = describe_component("labeled_input")
        self.assertIsNotNone(labeled_input.data_attributes_doc)
        self.assertEqual(labeled_input.data_attributes_doc, labeled_input.aria_attributes_doc)
        self.assertEqual(labeled_input.react_docs_url, f"{STORYBOOK}form-labeledinput--docs")
        self.assertIsNone(describe_component("button").data_attributes_doc)

    def test_layout_parts_have_no_react_docs(self):
        for name in ("content", "heading", "header", "footer"):
            with self.subTest(component=name):
                reference = describe_component(name)
                self.assertIsNone(reference.react_docs_url)
                self.assertEqual(reference.react_tag, f'component "@alliancesoftware/ui" "{name.title()}"')

    def test_unknown_component(self):
        with self.assertRaisesMessage(LookupError, "No static ui component is registered as 'carousel'"):
            describe_component("carousel")

    def test_component_of_another_registry(self):
        registry = HtmlUIComponentRegistry()
        registry.register_renderer("stat", StatRenderer)

        reference = describe_component("stat", registry)

        self.assertIsNone(reference.react_tag)
        self.assertIsNone(reference.react_docs_url)
        self.assertEqual(reference.apui_marker, "stat")
        self.assertEqual(
            [prop.template_name for prop in reference.props], ["class", "label", "size", "style"]
        )
        self.assertEqual(self.props(reference)["size"].values, ('``"md"``', '``"lg"``'))
        self.assertEqual(reference.forwarded_attributes, ("id", "title"))
        with self.assertRaises(LookupError):
            describe_component("button", registry)

    def test_load_registry(self):
        self.assertIs(
            load_registry("alliance_platform.ui.html_components.built_in_registry"), built_in_registry
        )
        with self.assertRaisesMessage(ValueError, "is not an HtmlUIComponentRegistry"):
            load_registry("alliance_platform.ui.html_components.base")
        with self.assertRaisesMessage(ValueError, "is not a dotted path to a registry"):
            load_registry("built_in_registry")
        with self.assertRaises(ImportError):
            load_registry("alliance_platform.ui.no_such_module.registry")

    def test_template_prop_names_are_what_templates_write(self):
        self.assertEqual(template_prop_name("className"), "class")
        self.assertEqual(template_prop_name("formEncType"), "form_enc_type")
        self.assertEqual(template_prop_name("aria-label"), "aria_label")
        for name, renderer in built_in_renderers().items():
            names = (
                renderer.documented_props()
                | set(renderer.prop_aliases)
                | set(renderer.deprecated_prop_aliases)
            )
            for prop in names:
                with self.subTest(component=name, prop=prop):
                    self.assertEqual(
                        renderer.canonical_prop_name(template_prop_name(prop)),
                        renderer.canonical_prop_name(prop),
                    )


class ComponentReferenceRstTestCase(SimpleTestCase):
    def test_component_reference(self):
        lines = component_reference_rst(describe_component("text_area"))
        component_tag = '{% component "@alliancesoftware/ui" "TextArea" %}'

        self.assertEqual(
            lines[:5],
            [
                ':Usage: ``{% ui "text_area" %}`` (a leaf: no children and no ``{% endui %}``)',
                ':Marker: ``data-apui="text-area"``',
                ':Runtime: ``data-apui-attach="text-area"``',
                f":React: ``{component_tag}``, `React docs <{STORYBOOK}ui-textarea--docs>`__",
                "",
            ],
        )
        self.assertIn(".. list-table::", lines)
        rows = lines.index("    * - ``rows``")
        self.assertEqual(
            lines[rows : rows + 4],
            [
                "    * - ``rows``",
                "      -",
                "      -",
                f"      - static only: {UITextAreaRenderer.prop_docs['rows']}",
            ],
        )
        is_disabled = lines.index("    * - ``is_disabled``")
        self.assertEqual(
            lines[is_disabled : is_disabled + 6],
            [
                "    * - ``is_disabled``",
                "",
                "        ``isDisabled``",
                "      -",
                "      -",
                "      - deprecated alias ``disabled``; see React docs",
            ],
        )
        self.assertIn("* ``data-*`` attributes", lines)
        self.assertIn(
            "* ``on_*`` props: event handlers are not supported by static input components; "
            f"use ``{component_tag}`` instead",
            lines,
        )

    def test_named_react_tag_links_to_its_section(self):
        reference = describe_component("button")

        linked = component_reference_rst(reference, link_react_tag=True)
        plain = component_reference_rst(reference)

        docs = f"`React docs <{STORYBOOK}ui-button--docs>`__"
        self.assertIn(f":React: :ttag:`{{% Button %}} <Button>`, {docs}", linked)
        self.assertIn(f":React: ``{{% Button %}}``, {docs}", plain)

    def test_component_without_props_or_attributes(self):
        lines = component_reference_rst(describe_component("table_header"))

        self.assertIn(':Parent: renders only inside ``{% ui "table" %}``', lines)
        self.assertIn("Props: none.", lines)
        self.assertIn("Forwarded attributes: none.", lines)
        self.assertNotIn(".. list-table::", lines)

    def test_component_without_a_react_equivalent(self):
        class DocumentedStatRenderer(StatRenderer):
            prop_docs = {"label": "The text shown above\n the figure."}
            unsupported_prop_reasons = {"chart": "charts need *JavaScript*; see my_app"}

        registry = HtmlUIComponentRegistry()
        registry.register_renderer("stat", DocumentedStatRenderer)

        lines = component_reference_rst(describe_component("stat", registry))

        self.assertFalse(any(line.startswith(":React:") for line in lines))
        # Its own props are described without "static only", and the others without React docs
        self.assertIn("      - The text shown above the figure.", lines)
        self.assertNotIn("see React docs", "\n".join(lines))
        self.assertNotIn("as in React", "\n".join(lines))
        # A refusal reason is plain text, escaped, and has no React tag to suggest
        self.assertIn(r"* ``chart``: charts need \*JavaScript\*; see my\_app", lines)
