from __future__ import annotations

import warnings

from tests.parity.base import HtmlUIParityTestCase


class UIInputComponentsTestCase(HtmlUIParityTestCase):
    """Focused unit tests for input component behaviour not covered by the parity fixtures."""

    def render_with_warnings(self, template_body: str, context_kwargs=None):
        with self.setup_render_context():
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                output = self.render_ui_template(template_body, context_kwargs)
        return output, [str(item.message) for item in caught_warnings]

    def test_class_kwarg_merges_with_default_classes(self):
        output, caught = self.render_with_warnings(
            '{% ui "text_input" label="Email" class="extra-class" %}{% endui %}'
        )
        self.assertIn(
            'class="LabeledInput_labeledInput LabeledInput_labeledInput_inputSize_sm '
            'LabeledInput_labeledInput_labelPosition_top extra-class"',
            output,
        )
        self.assertEqual(caught, [])

    def test_class_and_class_name_kwargs_merge_together(self):
        output, _ = self.render_with_warnings(
            '{% ui "text_input" label="Email" class="one" className="two" %}{% endui %}'
        )
        self.assertIn("one two", output)

    def test_input_class_name_merges_onto_control_only(self):
        output, _ = self.render_with_warnings(
            '{% ui "text_input" label="Email" inputClassName="custom-input" %}{% endui %}'
        )
        self.assertIn('class="TextInputBase_input custom-input"', output)
        self.assertNotIn("LabeledInput_labeledInput custom-input", output)

    def test_react_only_props_warn_and_are_ignored(self):
        output, caught = self.render_with_warnings(
            '{% ui "text_input" label="Email" renderInput=render_input inputProps=input_props %}{% endui %}',
            {"render_input": lambda data: data, "input_props": {"rows": 4}},
        )
        self.assertIn("Prop 'renderInput' is not supported by HTML ui components and will be ignored", caught)
        self.assertIn("Prop 'inputProps' is not supported by HTML ui components and will be ignored", caught)
        self.assertNotIn("renderInput", output)
        self.assertNotIn("rows", output)

    def test_non_scalar_prop_values_warn_and_are_ignored(self):
        output, caught = self.render_with_warnings(
            '{% ui "text_input" label="Email" someProp=bad_value %}{% endui %}',
            {"bad_value": {"nested": "dict"}},
        )
        self.assertIn(
            "Prop 'someProp' with non-scalar value is not supported by HTML ui components "
            "and will be ignored",
            caught,
        )
        self.assertNotIn("someProp", output)
        self.assertNotIn("someprop", output)

    def test_allowlisted_props_pass_through_to_control(self):
        output, caught = self.render_with_warnings(
            '{% ui "text_input" label="Email" autoComplete="email" maxLength=20 spellCheck="false" '
            'pattern="[a-z]+" %}{% endui %}'
        )
        self.assertIn('autocomplete="email"', output)
        self.assertIn('maxlength="20"', output)
        self.assertIn('spellcheck="false"', output)
        self.assertIn('pattern="[a-z]+"', output)
        self.assertEqual(caught, [])

    def test_data_and_aria_props_pass_through_to_control(self):
        output, caught = self.render_with_warnings(
            '{% ui "text_input" label="Email" data_testid="email-field" aria_label="Email address" %}{% endui %}'
        )
        self.assertIn('data-testid="email-field"', output)
        self.assertIn('aria-label="Email address"', output)
        self.assertEqual(caught, [])

    def test_event_handler_props_warn_and_are_never_rendered(self):
        output, caught = self.render_with_warnings(
            '{% ui "text_input" label="Email" onClick="alert(1)" on_input="alert(2)" %}{% endui %}'
        )
        self.assertIn(
            "Event handler prop 'onClick' is not supported by HTML ui components and will be ignored",
            caught,
        )
        self.assertIn(
            "Event handler prop 'onInput' is not supported by HTML ui components and will be ignored",
            caught,
        )
        self.assertNotIn("onclick", output.lower())
        self.assertNotIn("oninput", output.lower())
        self.assertNotIn("alert", output)

    def test_unknown_props_warn_and_are_ignored(self):
        output, caught = self.render_with_warnings(
            '{% ui "text_input" label="Email" unknownAttr="nope" %}{% endui %}'
        )
        self.assertIn(
            "Prop 'unknownAttr' is not a supported 'text-input' attribute and will be ignored",
            caught,
        )
        self.assertNotIn("unknownattr", output.lower())

    def test_pattern_is_not_allowed_on_text_area(self):
        output, caught = self.render_with_warnings(
            '{% ui "text_area" label="Notes" pattern="[a-z]+" %}{% endui %}'
        )
        self.assertIn(
            "Prop 'pattern' is not a supported 'text-area' attribute and will be ignored",
            caught,
        )
        self.assertNotIn("pattern", output)

    def test_generated_ids_are_unique_within_a_template_render(self):
        output, _ = self.render_with_warnings(
            '{% ui "text_input" label="First" description="one" %}{% endui %}'
            '{% ui "text_input" label="Second" description="two" %}{% endui %}'
        )
        self.assertIn('id="apui-text-input-1"', output)
        self.assertIn('id="apui-text-input-2"', output)
        self.assertIn('id="apui-text-input-3"', output)
        self.assertIn('id="apui-text-input-4"', output)
        self.assertIn('for="apui-text-input-1"', output)
        self.assertIn('for="apui-text-input-3"', output)
        self.assertIn('aria-describedby="apui-text-input-2"', output)
        self.assertIn('aria-describedby="apui-text-input-4"', output)

    def test_caller_aria_describedby_is_preserved_and_generated_ids_appended(self):
        output, _ = self.render_with_warnings(
            '{% ui "text_input" label="Email" aria_describedby="external" description="Help" %}{% endui %}'
        )
        self.assertIn('aria-describedby="apui-text-input-2 external"', output)

    def test_caller_id_is_preserved(self):
        output, _ = self.render_with_warnings('{% ui "text_input" label="Email" id="custom-id" %}{% endui %}')
        self.assertIn('id="custom-id"', output)
        self.assertIn('for="custom-id"', output)
        self.assertNotIn("apui-text-input", output)

    def test_disabled_alias_warns_and_disables(self):
        output, caught = self.render_with_warnings(
            '{% ui "text_input" label="Email" disabled=True %}{% endui %}'
        )
        self.assertIn("You passed 'disabled' - use 'isDisabled' instead", caught)
        self.assertIn("<input", output)
        self.assertIn(" disabled", output)
        self.assertIn('data-disabled="true"', output)

    def test_invalid_enum_props_warn_and_fall_back(self):
        output, caught = self.render_with_warnings(
            '{% ui "text_input" label="Email" labelPosition="middle" inputSize="xl" '
            'labelAlign="center" validationState="unknown" %}{% endui %}'
        )
        self.assertEqual(
            caught,
            [
                "Invalid 'labelPosition' prop passed: middle",
                "Invalid 'labelAlign' prop passed: center",
                "Invalid 'inputSize' prop passed: xl",
                "Invalid 'validationState' prop passed: unknown",
            ],
        )
        self.assertIn('data-label-position="top"', output)
        self.assertIn('data-input-size="sm"', output)
        self.assertNotIn("data-label-align", output)
        self.assertNotIn("data-invalid", output)
        self.assertNotIn("data-valid", output)

    def test_is_loading_sets_aria_busy_and_data_loading(self):
        output, _ = self.render_with_warnings('{% ui "text_input" label="Email" isLoading=True %}{% endui %}')
        self.assertIn('aria-busy="true"', output)
        self.assertIn('data-loading="true"', output)

    def test_is_loading_when_disabled_keeps_aria_busy_but_not_data_loading(self):
        output, _ = self.render_with_warnings(
            '{% ui "text_input" label="Email" isLoading=True isDisabled=True %}{% endui %}'
        )
        self.assertIn('aria-busy="true"', output)
        self.assertNotIn("data-loading", output)

    def test_children_content_warns_and_is_ignored(self):
        output, caught = self.render_with_warnings(
            '{% ui "text_input" label="Email" %}unexpected content{% endui %}'
        )
        self.assertIn("'text-input' does not support children; the content will be ignored", caught)
        self.assertNotIn("unexpected content", output)

    def test_label_and_value_are_escaped(self):
        output, _ = self.render_with_warnings(
            '{% ui "text_input" label=label value=value %}{% endui %}',
            {"label": "<b>Email</b>", "value": '"><script>'},
        )
        self.assertIn("&lt;b&gt;Email&lt;/b&gt;", output)
        self.assertIn("&quot;&gt;&lt;script&gt;", output)
        self.assertNotIn("<b>Email</b>", output)
        self.assertNotIn("<script>", output)

    def test_text_area_rows_and_cols_pass_through(self):
        # The React TextArea drops rows/cols (it autosizes at runtime); the static renderer passes
        # them through as valid textarea attributes
        output, caught = self.render_with_warnings(
            '{% ui "text_area" label="Notes" rows=4 cols=40 %}{% endui %}'
        )
        self.assertIn('rows="4"', output)
        self.assertIn('cols="40"', output)
        self.assertEqual(caught, [])

    def test_text_area_content_is_escaped(self):
        output, _ = self.render_with_warnings(
            '{% ui "text_area" label="Notes" defaultValue=value %}{% endui %}',
            {"value": "</textarea><script>alert(1)</script>"},
        )
        self.assertIn("&lt;/textarea&gt;&lt;script&gt;alert(1)&lt;/script&gt;", output)
        self.assertNotIn("</textarea><script>", output)

    def test_text_area_numeric_height_gets_px_suffix(self):
        output, _ = self.render_with_warnings('{% ui "text_area" label="Notes" height=120 %}{% endui %}')
        self.assertIn('style="height: 120px"', output)

    def test_number_input_format_options_warns_and_is_ignored(self):
        output, caught = self.render_with_warnings(
            '{% ui "number_input" label="Price" formatOptions=format_options defaultValue=12.5 %}{% endui %}',
            {"format_options": {"style": "currency", "currency": "AUD"}},
        )
        self.assertIn(
            "'formatOptions' cannot be mapped to static HTML attributes and will be ignored", caught
        )
        self.assertIn('value="12.5"', output)
        self.assertNotIn("currency", output)

    def test_number_input_min_max_step_accepted_without_dom_output(self):
        output, caught = self.render_with_warnings(
            '{% ui "number_input" label="Qty" minValue=1 maxValue=20 step=2 %}{% endui %}'
        )
        self.assertEqual(caught, [])
        self.assertNotIn("minValue", output)
        self.assertNotIn("min=", output)
        self.assertNotIn("max=", output)
        self.assertNotIn("step=", output)

    def test_number_input_hidden_input_only_when_name_given(self):
        output_with_name, _ = self.render_with_warnings(
            '{% ui "number_input" label="Qty" name="qty" %}{% endui %}'
        )
        self.assertIn('<input type="hidden" name="qty" value=""', output_with_name)
        # The visible input must not carry the name so only the hidden input value is submitted
        self.assertEqual(output_with_name.count('name="qty"'), 1)

        output_without_name, _ = self.render_with_warnings('{% ui "number_input" label="Qty" %}{% endui %}')
        self.assertNotIn('type="hidden"', output_without_name)

    def test_number_input_zero_value_renders(self):
        output, _ = self.render_with_warnings(
            '{% ui "number_input" label="Qty" name="qty" value=0 %}{% endui %}'
        )
        self.assertIn('<input type="hidden" name="qty" value="0"', output)

    def test_number_input_integer_float_value_renders_without_decimal(self):
        output, _ = self.render_with_warnings(
            '{% ui "number_input" label="Qty" defaultValue=5.0 %}{% endui %}'
        )
        self.assertIn('value="5"', output)

    def test_number_input_hide_step_buttons(self):
        output, _ = self.render_with_warnings(
            '{% ui "number_input" label="Qty" hideStepButtons=True %}{% endui %}'
        )
        self.assertNotIn("data-direction", output)
        # The addon-after container still renders (and data-has-addon-after is still set),
        # matching the React component
        self.assertIn('data-has-addon-after="true"', output)

    def test_number_input_step_buttons_disabled_when_input_disabled(self):
        output, _ = self.render_with_warnings(
            '{% ui "number_input" label="Qty" isDisabled=True %}{% endui %}'
        )
        self.assertIn('<button type="button" disabled', output)

    def test_none_valued_props_are_treated_as_unset(self):
        output, caught = self.render_with_warnings(
            '{% ui "text_input" label="Email" placeholder=missing_value labelAlign=missing_value %}{% endui %}',
            {"missing_value": None},
        )
        self.assertEqual(caught, [])
        self.assertNotIn("placeholder", output)
        self.assertNotIn("data-label-align", output)
