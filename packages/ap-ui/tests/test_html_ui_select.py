from __future__ import annotations

from bs4 import BeautifulSoup

from tests.parity.base import HtmlUIParityTestCase

COLOUR_OPTIONS = (
    '<option value="red">Red</option><option value="green">Green</option><option value="blue">Blue</option>'
)


class UINativeSelectTestCase(HtmlUIParityTestCase):
    """Behaviour of ``select`` the parity fixtures do not show."""

    def render_with_diagnostics(self, template_body: str, context_kwargs=None) -> tuple[str, list[str]]:
        with self.setup_render_context():
            with self.capture_diagnostics() as diagnostics:
                output = self.render_ui_template(template_body, context_kwargs)
        return output, diagnostics

    def selected_values(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        return [str(option.get("value", option.get_text())) for option in soup.select("option[selected]")]

    def test_options_render_as_written_without_a_value(self):
        # As Django's select widget writes them, the options carry their own selected attributes
        options = (
            '<option value="red">Red</option>\n'
            '<option value="green" selected data-colour="#0f0">Green</option>\n'
            "<!-- the last option -->\n"
            "<option value='blue'>Blue</option>"
        )
        output, diagnostics = self.render_with_diagnostics(
            f'{{% ui "select" label="Colour" %}}{options}{{% endui %}}'
        )

        self.assertIn(f">{options}</select>", output)
        self.assertEqual(diagnostics, [])

    def test_value_replaces_the_selected_attributes_of_the_options(self):
        # React marks the options of a select with a value and ignores their own selected
        output, diagnostics = self.render_with_diagnostics(
            '{% ui "select" label="Colour" value="blue" %}'
            '<option value="red" selected>Red</option><option value="green" selected="selected">Green</option>'
            '<option value="blue">Blue</option>{% endui %}'
        )

        self.assertEqual(self.selected_values(output), ["blue"])
        self.assertIn(
            '<option value="red">Red</option><option value="green">Green</option>'
            '<option value="blue" selected>Blue</option>',
            output,
        )
        self.assertEqual(diagnostics, [])

    def test_value_leaves_the_other_options_as_written(self):
        output, _ = self.render_with_diagnostics(
            '{% ui "select" label="Colour" value="green" %}'
            "<option value='red' data-x = \"1\">Red</option>"
            '<option   value="green"  title="Go">Green</option>{% endui %}'
        )

        self.assertIn("<option value='red' data-x = \"1\">Red</option>", output)
        self.assertIn('<option value="green" title="Go" selected>Green</option>', output)

    def test_value_matches_the_text_of_an_option_without_a_value(self):
        output, _ = self.render_with_diagnostics(
            '{% ui "select" label="Size" value="Extra large" %}'
            "<option>Small</option><option>\n  Extra\n  large\n</option>{% endui %}"
        )

        self.assertEqual(self.selected_values(output), ["\n  Extra\n  large\n"])

    def test_value_matches_values_with_character_references(self):
        output, _ = self.render_with_diagnostics(
            '{% ui "select" label="Pair" value=pair %}'
            '<option value="a&amp;b">A and B</option><option value="a">A</option>{% endui %}',
            {"pair": "a&b"},
        )

        self.assertIn('<option value="a&amp;b" selected>A and B</option>', output)

    def test_value_is_compared_as_text(self):
        output, _ = self.render_with_diagnostics(
            '{% ui "select" label="Count" value=2 %}'
            '<option value="1">One</option><option value="2">Two</option>{% endui %}'
        )

        self.assertEqual(self.selected_values(output), ["2"])

    def test_default_value_selects_like_value(self):
        output, _ = self.render_with_diagnostics(
            f'{{% ui "select" label="Colour" default_value="green" %}}{COLOUR_OPTIONS}{{% endui %}}'
        )

        self.assertEqual(self.selected_values(output), ["green"])

    def test_value_wins_over_default_value(self):
        output, _ = self.render_with_diagnostics(
            '{% ui "select" label="Colour" value="red" default_value="green" %}'
            f"{COLOUR_OPTIONS}{{% endui %}}"
        )

        self.assertEqual(self.selected_values(output), ["red"])

    def test_values_of_a_multiple_select(self):
        for values, expected in [
            (["red", "blue"], ["red", "blue"]),
            (("green",), ["green"]),
            # A single value selects one option
            ("blue", ["blue"]),
            ([], []),
        ]:
            with self.subTest(values=values):
                output, diagnostics = self.render_with_diagnostics(
                    f'{{% ui "select" label="Colours" is_multiple=True value=values %}}{COLOUR_OPTIONS}'
                    "{% endui %}",
                    {"values": values},
                )
                self.assertEqual(self.selected_values(output), expected)
                self.assertEqual(diagnostics, [])

    def test_a_list_of_one_value_selects_an_option_of_a_single_select(self):
        # Django's select widgets give their value as a list
        output, diagnostics = self.render_with_diagnostics(
            f'{{% ui "select" label="Colour" value=values %}}{COLOUR_OPTIONS}{{% endui %}}',
            {"values": ["green"]},
        )

        self.assertEqual(self.selected_values(output), ["green"])
        self.assertEqual(diagnostics, [])

    def test_several_values_for_a_single_select_are_reported(self):
        output, diagnostics = self.render_with_diagnostics(
            f'{{% ui "select" label="Colour" value=values %}}{COLOUR_OPTIONS}{{% endui %}}',
            {"values": ["red", "blue"]},
        )

        # As React, every option named is selected, and the browser shows the last
        self.assertEqual(self.selected_values(output), ["red", "blue"])
        self.assertEqual(diagnostics, ["Prop 'value' must be a single value unless 'isMultiple' is set"])

    def test_a_value_list_of_other_values_is_refused(self):
        output, diagnostics = self.render_with_diagnostics(
            f'{{% ui "select" label="Colour" value=values %}}{COLOUR_OPTIONS}{{% endui %}}',
            {"values": [{"colour": "red"}]},
        )

        self.assertEqual(self.selected_values(output), [])
        self.assertEqual(
            diagnostics,
            [
                "Prop 'value' with non-scalar value is not supported by static input components and will be ignored"
            ],
        )

    def test_multiple_attribute_from_widget_attrs(self):
        # Django's SelectMultiple widget sets the native attribute in its attrs
        output, diagnostics = self.render_with_diagnostics(
            f'{{% ui "select" props=attrs label="Colours" %}}{COLOUR_OPTIONS}{{% endui %}}',
            {"attrs": {"multiple": True, "id": "id_colours", "required": True}},
        )

        soup = BeautifulSoup(output, "html.parser")
        select = soup.select_one("select")
        assert select is not None
        self.assertTrue(select.has_attr("multiple"))
        self.assertEqual(select["aria-required"], "true")
        # A list box has no chevron
        self.assertIsNone(soup.select_one(".NativeSelect_chevron"))
        self.assertEqual(diagnostics, [])

    def test_size_above_one_is_a_list_box(self):
        for size, has_chevron in [(1, True), ("1", True), (4, False), ("2", False), ("rows", True)]:
            with self.subTest(size=size):
                output, _ = self.render_with_diagnostics(
                    f'{{% ui "select" label="Colour" size=size %}}{COLOUR_OPTIONS}{{% endui %}}',
                    {"size": size},
                )
                self.assertIn(f'size="{size}"', output)
                self.assertEqual("NativeSelect_chevron" in output, has_chevron)

    def test_placeholder_and_read_only_are_not_select_props(self):
        output, diagnostics = self.render_with_diagnostics(
            '{% ui "select" label="Colour" placeholder="Choose" is_read_only=True read_only=True %}'
            f"{COLOUR_OPTIONS}{{% endui %}}"
        )

        self.assertNotIn("placeholder", output)
        self.assertNotIn("readonly", output)
        self.assertEqual(
            diagnostics,
            [
                f"Prop '{prop}' is not a supported 'select' attribute and will be ignored"
                for prop in ("placeholder", "isReadOnly", "readOnly")
            ],
        )

    def test_event_handlers_and_react_only_props_name_the_react_tag(self):
        output, diagnostics = self.render_with_diagnostics(
            '{% ui "select" label="Colour" on_change="alert(1)" input_ref="ref" %}'
            f"{COLOUR_OPTIONS}{{% endui %}}"
        )

        self.assertNotIn("alert", output)
        self.assertEqual(
            diagnostics,
            [
                "Prop 'onChange' will be ignored: event handlers are not supported by static input "
                'components; use {% component "@alliancesoftware/ui" "NativeSelect" %} instead',
                "Prop 'inputRef' will be ignored: React-only props are not supported by static input "
                'components; use {% component "@alliancesoftware/ui" "NativeSelect" %} instead',
            ],
        )

    def test_select_attributes_pass_through(self):
        output, diagnostics = self.render_with_diagnostics(
            '{% ui "select" label="Colour" auto_focus=True tab_index=2 lang="en" dir="ltr" '
            'data_testid="colour" aria_label="Colour choice" %}'
            f"{COLOUR_OPTIONS}{{% endui %}}"
        )

        select = BeautifulSoup(output, "html.parser").select_one("select")
        assert select is not None
        self.assertEqual(
            {
                name: select.get(name)
                for name in ("autofocus", "tabindex", "lang", "dir", "data-testid", "aria-label")
            },
            {
                "autofocus": "",
                "tabindex": "2",
                "lang": "en",
                "dir": "ltr",
                "data-testid": "colour",
                "aria-label": "Colour choice",
            },
        )
        self.assertEqual(diagnostics, [])

    def test_options_from_template_variables_are_escaped(self):
        output, _ = self.render_with_diagnostics(
            '{% ui "select" label="Colour" value=chosen %}'
            '{% for value, label in choices %}<option value="{{ value }}">{{ label }}</option>{% endfor %}'
            "{% endui %}",
            {"choices": [("<b>", "<b>bold</b>"), ("plain", "Plain")], "chosen": "<b>"},
        )

        self.assertIn('<option value="&lt;b&gt;" selected>&lt;b&gt;bold&lt;/b&gt;</option>', output)
