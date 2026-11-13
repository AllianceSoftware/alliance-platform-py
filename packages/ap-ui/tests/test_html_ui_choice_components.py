from __future__ import annotations

from bs4 import BeautifulSoup
from django.utils.safestring import mark_safe

from tests.parity.base import HtmlUIParityTestCase

CHECKBOX_REACT_TAG = '{% component "@alliancesoftware/ui" "Checkbox" %}'


class UIChoiceComponentsTestCase(HtmlUIParityTestCase):
    """Unit tests for the static checkbox and radio components not covered by the parity fixtures."""

    def render_with_diagnostics(
        self, template_body: str, context_kwargs=None
    ) -> tuple[BeautifulSoup, list[str]]:
        with self.setup_render_context():
            with self.capture_diagnostics() as diagnostics:
                output = self.render_ui_template(template_body, context_kwargs)
        return BeautifulSoup(output, "html.parser"), diagnostics

    def test_checkbox_takes_the_checked_attribute_django_sets(self):
        soup, diagnostics = self.render_with_diagnostics(
            '{% ui "checkbox" props=attrs %}Accept{% endui %}', {"attrs": {"checked": True, "required": True}}
        )
        self.assertEqual(diagnostics, [])
        checkbox = soup.select_one("input")
        assert checkbox is not None
        self.assertTrue(checkbox.has_attr("checked"))
        # As React's Checkbox, required is announced rather than enforced by the browser
        self.assertEqual(checkbox["aria-required"], "true")
        self.assertFalse(checkbox.has_attr("required"))

    def test_checkbox_is_selected_wins_over_default_selected(self):
        soup, _ = self.render_with_diagnostics(
            '{% ui "checkbox" is_selected=False default_selected=True %}Accept{% endui %}'
        )
        checkbox = soup.select_one("input")
        assert checkbox is not None
        self.assertFalse(checkbox.has_attr("checked"))

    def test_checkbox_accepts_the_label_form_input_passes_without_rendering_it(self):
        soup, diagnostics = self.render_with_diagnostics(
            '{% ui "checkbox" label="Accept" %}Accept the terms{% endui %}'
        )
        self.assertEqual(diagnostics, [])
        self.assertEqual(soup.get_text(), "Accept the terms")

    def test_checkbox_help_text_gets_a_generated_id_without_one_given(self):
        soup, diagnostics = self.render_with_diagnostics(
            '{% ui "checkbox" description="One email a month" %}Subscribe{% endui %}'
            '{% ui "checkbox" is_invalid=True error_message="Choose one" %}Agree{% endui %}'
        )
        self.assertEqual(diagnostics, [])
        inputs = soup.select("input")
        help_texts = soup.select(".LabeledInput_helpText")
        self.assertEqual(
            [help_text.get_text() for help_text in help_texts], ["One email a month", "Choose one"]
        )
        for control, help_text in zip(inputs, help_texts):
            self.assertRegex(help_text["id"], r"^apui-checkbox-\d+$")
            self.assertEqual(control["aria-describedby"], help_text["id"])
        self.assertNotEqual(help_texts[0]["id"], help_texts[1]["id"])

    def test_checkbox_help_text_is_named_after_its_id_and_listed_once(self):
        soup, diagnostics = self.render_with_diagnostics(
            '{% ui "checkbox" id="id_terms" aria_describedby="id_terms_helptext id_terms_error id_extra" '
            'description="Read them first" error_message="This field is required." is_invalid=True %}'
            "I accept the terms{% endui %}"
        )
        self.assertEqual(diagnostics, [])
        error = soup.find(id="id_terms_error")
        assert error is not None
        self.assertEqual(error.get_text(), "This field is required.")
        # The error message replaces the help text while the checkbox is invalid
        self.assertIsNone(soup.find(id="id_terms_helptext"))
        self.assertEqual(
            soup.select_one("input")["aria-describedby"], "id_terms_error id_terms_helptext id_extra"
        )
        row = error.parent
        assert row is not None
        self.assertEqual(row["data-invalid"], "true")
        self.assertEqual(row["data-label-position"], "top")

    def test_checkbox_error_message_waits_for_the_invalid_state(self):
        soup, _ = self.render_with_diagnostics(
            '{% ui "checkbox" id="id_terms" error_message="This field is required." %}Agree{% endui %}'
        )
        self.assertIsNone(soup.find(id="id_terms_error"))
        self.assertFalse(soup.select_one("input").has_attr("aria-describedby"))
        self.assertFalse(soup.select_one('[data-label-position="top"]').has_attr("data-invalid"))

    def test_checkbox_help_text_takes_rich_content(self):
        soup, diagnostics = self.render_with_diagnostics(
            '{% ui "checkbox" id="id_terms" description=help %}Agree{% endui %}',
            {"help": mark_safe('Read the <a href="/terms/">terms</a>')},
        )
        self.assertEqual(diagnostics, [])
        help_text = soup.find(id="id_terms_helptext")
        assert help_text is not None
        self.assertEqual(help_text.decode_contents(), 'Read the <a href="/terms/">terms</a>')

    def test_checkbox_in_a_group_renders_no_help_text_of_its_own(self):
        soup, diagnostics = self.render_with_diagnostics(
            '{% ui "checkbox_group" label="Pets" name="pets" %}'
            '{% ui "checkbox" value="cat" description="Cats only" is_invalid=True error_message="Bad" %}'
            "Cat{% endui %}{% endui %}"
        )
        self.assertEqual(diagnostics, [])
        self.assertEqual(soup.select(".LabeledInput_helpText"), [])
        self.assertFalse(soup.select_one("input").has_attr("aria-describedby"))

    def test_checkbox_input_attributes(self):
        soup, diagnostics = self.render_with_diagnostics(
            '{% ui "checkbox" name="terms" form="signup" auto_focus=True exclude_from_tab_order=True '
            'data_testid="terms" aria_details="terms-details" %}Accept{% endui %}'
        )
        self.assertEqual(diagnostics, [])
        checkbox = soup.select_one("input")
        assert checkbox is not None
        self.assertEqual(checkbox["form"], "signup")
        self.assertTrue(checkbox.has_attr("autofocus"))
        self.assertEqual(checkbox["tabindex"], "-1")
        self.assertEqual(checkbox["data-testid"], "terms")
        self.assertEqual(checkbox["aria-details"], "terms-details")

    def test_checkbox_refuses_react_only_props_and_event_handlers(self):
        soup, diagnostics = self.render_with_diagnostics(
            '{% ui "checkbox" parent_is_hovered=True on_change="toggle()" %}Accept{% endui %}'
        )
        self.assertEqual(
            diagnostics,
            [
                "Prop 'parentIsHovered' will be ignored: React-only props are not supported by static "
                f"checkboxes; use {CHECKBOX_REACT_TAG} instead",
                "Prop 'onChange' will be ignored: event handlers are not supported by static checkboxes; "
                f"use {CHECKBOX_REACT_TAG} instead",
            ],
        )
        root = soup.select_one('[data-apui="checkbox"]')
        assert root is not None
        self.assertFalse(root.has_attr("data-hovered"))
        self.assertNotIn("onchange", str(soup))

    def test_checkbox_in_a_group_reports_its_own_selection_as_react_does(self):
        soup, diagnostics = self.render_with_diagnostics(
            '{% ui "checkbox_group" label="Pets" name="pets" %}'
            '{% ui "checkbox" value="cat" is_selected=True default_selected=True %}Cat{% endui %}'
            "{% endui %}"
        )
        self.assertEqual(
            diagnostics,
            [
                "When <Checkbox> is used within a <CheckboxGroup>, the following keys must be applied at "
                "the <CheckboxGroup> level rather than <Checkbox>: isSelected, defaultSelected"
            ],
        )
        checkbox = soup.select_one("input")
        assert checkbox is not None
        self.assertFalse(checkbox.has_attr("checked"))

    def test_checkbox_group_values(self):
        template = (
            '{% ui "checkbox_group" label="Numbers" name="numbers" value=checked %}'
            '{% ui "checkbox" value=1 %}One{% endui %}{% ui "checkbox" value=2 %}Two{% endui %}'
            "{% endui %}"
        )
        for checked, expected in [([2], ["2"]), ((1, 2), ["1", "2"]), ("1", ["1"]), (None, [])]:
            with self.subTest(checked=checked):
                soup, diagnostics = self.render_with_diagnostics(template, {"checked": checked})
                self.assertEqual(diagnostics, [])
                self.assertEqual([box["value"] for box in soup.select("input[checked]")], expected)

    def test_checkbox_in_a_group_keeps_its_own_name_and_disabled_state(self):
        soup, _ = self.render_with_diagnostics(
            '{% ui "checkbox_group" label="Pets" name="pets" %}'
            '{% ui "checkbox" value="cat" name="cats" is_disabled=True %}Cat{% endui %}'
            "{% endui %}"
        )
        checkbox = soup.select_one("input")
        assert checkbox is not None
        self.assertEqual(checkbox["name"], "cats")
        self.assertTrue(checkbox.has_attr("disabled"))

    def test_read_only_checkbox_disables_its_input_and_submits_its_value_from_a_hidden_input(self):
        soup, diagnostics = self.render_with_diagnostics(
            '{% ui "checkbox" name="terms" value="yes" form="signup" is_read_only=True '
            "default_selected=True %}Accept{% endui %}"
        )
        self.assertEqual(diagnostics, [])
        root = soup.select_one('[data-apui="checkbox"]')
        assert root is not None
        checkbox, hidden = root.select("input")
        # HTML has no read only state for a checkbox, so disabling it is what stops it changing
        self.assertEqual(checkbox["type"], "checkbox")
        self.assertTrue(checkbox.has_attr("disabled"))
        self.assertTrue(checkbox.has_attr("checked"))
        self.assertEqual(checkbox["aria-readonly"], "true")
        # The stylesheet keeps the enabled look of a root that is read only and not disabled
        self.assertEqual(root["data-readonly"], "true")
        self.assertFalse(root.has_attr("data-disabled"))
        # A disabled input is not submitted, so a hidden input after it submits the value
        self.assertIs(checkbox.next_sibling, hidden)
        self.assertEqual(hidden.attrs, {"type": "hidden", "name": "terms", "value": "yes", "form": "signup"})

    def test_read_only_checkbox_without_a_value_submits_on_as_the_browser_does(self):
        for value_prop in ("", " value=None", " value=False"):
            with self.subTest(value_prop=value_prop):
                soup, _ = self.render_with_diagnostics(
                    f'{{% ui "checkbox" name="terms"{value_prop} is_read_only=True is_selected=True %}}'
                    "Accept{% endui %}"
                )
                checkbox, hidden = soup.select("input")
                self.assertFalse(checkbox.has_attr("value"))
                self.assertEqual(hidden.attrs, {"type": "hidden", "name": "terms", "value": "on"})

    def test_read_only_checkbox_that_submits_nothing_renders_no_hidden_input(self):
        for props, is_disabled in [
            # Not checked
            (' name="terms" is_read_only=True', False),
            # No name
            (" is_read_only=True default_selected=True", False),
            (' name="" is_read_only=True default_selected=True', False),
            # Disabled as well: it renders as a disabled checkbox, which submits nothing
            (' name="terms" is_read_only=True is_disabled=True default_selected=True', True),
        ]:
            with self.subTest(props=props):
                soup, diagnostics = self.render_with_diagnostics(
                    f'{{% ui "checkbox"{props} %}}Accept{{% endui %}}'
                )
                self.assertEqual(diagnostics, [])
                (checkbox,) = soup.select("input")
                self.assertTrue(checkbox.has_attr("disabled"))
                root = soup.select_one('[data-apui="checkbox"]')
                assert root is not None
                self.assertEqual(root["data-readonly"], "true")
                self.assertEqual(root.has_attr("data-disabled"), is_disabled)

    def test_read_only_checkbox_group_submits_each_checked_value(self):
        soup, diagnostics = self.render_with_diagnostics(
            '{% ui "checkbox_group" label="Pets" name="pets" value=checked is_read_only=True %}'
            '{% ui "checkbox" value="cat" %}Cat{% endui %}'
            '{% ui "checkbox" value="dog" %}Dog{% endui %}'
            '{% ui "checkbox" value="fish" is_disabled=True %}Fish{% endui %}'
            '{% ui "checkbox" value="bird" name="birds" %}Bird{% endui %}'
            "{% endui %}",
            {"checked": ["cat", "fish", "bird"]},
        )
        self.assertEqual(diagnostics, [])
        checkboxes = soup.select('input[type="checkbox"]')
        self.assertEqual([box["value"] for box in checkboxes], ["cat", "dog", "fish", "bird"])
        for checkbox in checkboxes:
            self.assertTrue(checkbox.has_attr("disabled"))
            self.assertEqual(checkbox["aria-readonly"], "true")
        # The checked checkboxes that are not disabled themselves, each under its own name
        self.assertEqual(
            [(hidden["name"], hidden["value"]) for hidden in soup.select('input[type="hidden"]')],
            [("pets", "cat"), ("birds", "bird")],
        )
        self.assertEqual(
            [root.has_attr("data-disabled") for root in soup.select('[data-apui="checkbox"]')],
            [False, False, True, False],
        )

    def test_read_only_checkbox_in_a_group_is_locked_on_its_own(self):
        soup, _ = self.render_with_diagnostics(
            '{% ui "checkbox_group" label="Pets" name="pets" value="cat" %}'
            '{% ui "checkbox" value="cat" is_read_only=True %}Cat{% endui %}'
            '{% ui "checkbox" value="dog" %}Dog{% endui %}'
            "{% endui %}"
        )
        cat, dog = soup.select('input[type="checkbox"]')
        self.assertTrue(cat.has_attr("disabled"))
        self.assertFalse(dog.has_attr("disabled"))
        (hidden,) = soup.select('input[type="hidden"]')
        self.assertEqual((hidden["name"], hidden["value"]), ("pets", "cat"))

    def test_read_only_radio_group_disables_its_radios_and_submits_the_checked_value(self):
        soup, diagnostics = self.render_with_diagnostics(
            '{% ui "radio_group" label="Colour" name="colour" default_value="green" is_read_only=True %}'
            '{% ui "radio" value="red" %}Red{% endui %}'
            '{% ui "radio" value="green" %}Green{% endui %}'
            "{% endui %}"
        )
        self.assertEqual(diagnostics, [])
        red, green = soup.select('input[type="radio"]')
        for radio in (red, green):
            self.assertTrue(radio.has_attr("disabled"))
        for root in soup.select('[data-apui="radio"]'):
            self.assertEqual(root["data-readonly"], "true")
            self.assertFalse(root.has_attr("data-disabled"))
        group = soup.select_one('[role="radiogroup"]')
        assert group is not None
        self.assertEqual(group["aria-readonly"], "true")
        self.assertFalse(group.has_attr("aria-disabled"))
        (hidden,) = soup.select('input[type="hidden"]')
        self.assertIs(green.next_sibling, hidden)
        self.assertEqual(hidden.attrs, {"type": "hidden", "name": "colour", "value": "green"})

    def test_read_only_radio_group_that_submits_nothing_renders_no_hidden_input(self):
        for group_props, radio_props in [
            # No radio is checked
            (" is_read_only=True", ""),
            # The checked radio is disabled, so it submits nothing, as in React
            (' is_read_only=True default_value="red"', " is_disabled=True"),
            # The group is disabled as well
            (' is_read_only=True is_disabled=True default_value="red"', ""),
        ]:
            with self.subTest(group_props=group_props, radio_props=radio_props):
                soup, diagnostics = self.render_with_diagnostics(
                    f'{{% ui "radio_group" label="Colour" name="colour"{group_props} %}}'
                    f'{{% ui "radio" value="red"{radio_props} %}}Red{{% endui %}}'
                    "{% endui %}"
                )
                self.assertEqual(diagnostics, [])
                (radio,) = soup.select("input")
                self.assertEqual(radio["type"], "radio")
                self.assertTrue(radio.has_attr("disabled"))

    def test_group_state_reaches_controls_in_an_include(self):
        soup, diagnostics = self.render_with_diagnostics(
            '{% ui "radio_group" label="Colour" name="colour" default_value="red" is_disabled=True %}'
            '{% include "test_widgets/radio_option.html" with value="red" only %}'
            "{% endui %}"
        )
        self.assertEqual(diagnostics, [])
        radio = soup.select_one("input")
        assert radio is not None
        self.assertEqual(radio["name"], "colour")
        self.assertTrue(radio.has_attr("checked"))
        self.assertTrue(radio.has_attr("disabled"))

    def test_radio_group_value_none_checks_no_radio(self):
        soup, diagnostics = self.render_with_diagnostics(
            '{% ui "radio_group" label="Colour" name="colour" value=None default_value="red" %}'
            '{% ui "radio" value="red" %}Red{% endui %}'
            "{% endui %}"
        )
        self.assertEqual(diagnostics, [])
        self.assertEqual(soup.select("input[checked]"), [])

    def test_radio_group_names_its_radios_after_a_generated_name_per_group(self):
        soup, _ = self.render_with_diagnostics(
            '{% ui "radio_group" label="First" %}{% ui "radio" value="a" %}A{% endui %}{% endui %}'
            '{% ui "radio_group" label="Second" %}{% ui "radio" value="b" %}B{% endui %}{% endui %}'
        )
        names = [radio["name"] for radio in soup.select("input")]
        self.assertEqual(len(set(names)), 2)
        for name in names:
            self.assertRegex(name, r"^apui-radio-group-\d+$")

    def test_radio_outside_a_radio_group_renders_nothing(self):
        soup, diagnostics = self.render_with_diagnostics('{% ui "radio" value="red" %}Red{% endui %}')
        self.assertEqual(str(soup), "")
        self.assertEqual(
            diagnostics,
            ["'radio' was rendered outside of a '{% ui \"radio_group\" %}' component; rendering nothing"],
        )

    def test_radio_without_a_value_is_reported(self):
        soup, diagnostics = self.render_with_diagnostics(
            '{% ui "radio_group" label="Colour" name="colour" %}{% ui "radio" %}Red{% endui %}{% endui %}'
        )
        self.assertEqual(diagnostics, ["'radio' needs a 'value', the value its group submits for it"])
        radio = soup.select_one("input")
        assert radio is not None
        self.assertFalse(radio.has_attr("value"))

    def test_group_without_a_label_is_labelled_by_the_caller(self):
        soup, diagnostics = self.render_with_diagnostics(
            '<h2 id="colour-heading">Colour</h2>'
            '{% ui "radio_group" aria_labelledby="colour-heading" name="colour" data_testid="colours" %}'
            '{% ui "radio" value="red" %}Red{% endui %}'
            "{% endui %}"
        )
        self.assertEqual(diagnostics, [])
        group = soup.select_one('[role="radiogroup"]')
        assert group is not None
        self.assertEqual(group["aria-labelledby"], "colour-heading")
        self.assertEqual(group["data-testid"], "colours")
        self.assertIsNone(soup.select_one('[data-apui="label"]'))

    def test_groups_accept_auto_focus_without_rendering_it(self):
        for template in [
            '{% ui "radio_group" label="Colour" name="colour" auto_focus=True %}'
            '{% ui "radio" value="red" %}Red{% endui %}{% endui %}',
            '{% ui "checkbox_group" label="Pets" name="pets" auto_focus=True %}'
            '{% ui "checkbox" value="cat" %}Cat{% endui %}{% endui %}',
        ]:
            with self.subTest(template=template):
                soup, diagnostics = self.render_with_diagnostics(template)
                self.assertEqual(diagnostics, [])
                self.assertEqual(soup.select("[autofocus]"), [])

    def test_group_help_text_takes_rich_content(self):
        soup, diagnostics = self.render_with_diagnostics(
            '{% ui "checkbox_group" label="Pets" name="pets" description=help %}'
            '{% ui "checkbox" value="cat" %}Cat{% endui %}'
            "{% endui %}",
            {"help": mark_safe("Any <strong>number</strong>")},
        )
        self.assertEqual(diagnostics, [])
        help_text = soup.select_one(".LabeledInput_helpText")
        assert help_text is not None
        self.assertEqual(help_text.decode_contents(), "Any <strong>number</strong>")
