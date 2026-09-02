from __future__ import annotations

from decimal import Decimal
import re
import warnings

from django.template import Context
from django.template import Template
from django.utils.translation import gettext_lazy

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
        self.assertIn(
            "Prop 'renderInput' will be ignored: React-only props are not supported by static input components",
            caught,
        )
        self.assertIn(
            "Prop 'inputProps' will be ignored: React-only props are not supported by static input components",
            caught,
        )
        self.assertNotIn("renderInput", output)
        self.assertNotIn("rows", output)

    def test_non_scalar_prop_values_warn_and_are_ignored(self):
        output, caught = self.render_with_warnings(
            '{% ui "text_input" label="Email" someProp=bad_value %}{% endui %}',
            {"bad_value": {"nested": "dict"}},
        )
        self.assertIn(
            "Prop 'someProp' with non-scalar value is not supported by static input components "
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
            "Prop 'onClick' will be ignored: event handlers are not supported by static input components",
            caught,
        )
        self.assertIn(
            "Prop 'onInput' will be ignored: event handlers are not supported by static input components",
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

    def test_repeated_included_input_partial_generates_document_unique_associated_ids(self):
        with self.setup_render_context():
            partial = Template(
                "{% load alliance_platform.ui %}"
                '{% ui "text_input" label=label description=description '
                "errorMessage=error validationState=validation_state %}{% endui %}"
            )
            output = self.render_ui_template(
                '{% include input with label="First" description="First help" validation_state=None %}'
                '{% include input with label="Second" description="Second help" '
                'error="Second error" validation_state="invalid" %}',
                {"input": partial},
            )

        generated_ids = re.findall(r'id="(apui-text-input-\d+)"', output)
        self.assertEqual(
            generated_ids,
            [
                "apui-text-input-1",
                "apui-text-input-2",
                "apui-text-input-3",
                "apui-text-input-4",
            ],
        )
        self.assertEqual(
            re.findall(r'<label[^>]+for="(apui-text-input-\d+)"', output),
            ["apui-text-input-1", "apui-text-input-3"],
        )
        self.assertEqual(
            re.findall(r'<input[^>]+aria-describedby="(apui-text-input-\d+)"', output),
            ["apui-text-input-2", "apui-text-input-4"],
        )
        self.assertIn('id="apui-text-input-2">First help</div>', output)
        self.assertIn('id="apui-text-input-4">Second error</div>', output)

    def test_generated_ids_survive_nested_include_only_boundaries(self):
        with self.setup_render_context():
            input_partial = Template(
                '{% load alliance_platform.ui %}{% ui "text_input" label="Included input" %}{% endui %}'
            )
            outer_partial = Template("{% include input_partial only %}")
            output = self.render_ui_template(
                "{% include outer_partial with input_partial=input_partial only %}"
                "{% include outer_partial with input_partial=input_partial only %}",
                {"outer_partial": outer_partial, "input_partial": input_partial},
            )

        self.assertEqual(
            re.findall(r'<input[^>]+id="(apui-text-input-\d+)"', output),
            ["apui-text-input-1", "apui-text-input-2"],
        )
        self.assertEqual(
            re.findall(r'<label[^>]+for="(apui-text-input-\d+)"', output),
            ["apui-text-input-1", "apui-text-input-2"],
        )

    def test_independent_template_renders_reset_generated_id_counter(self):
        with self.setup_render_context():
            template = Template(
                "{% load alliance_platform.ui %}"
                '{% ui "text_input" label="Email" description="Help" %}{% endui %}'
            )
            first = template.render(Context())
            second = template.render(Context())

        expected_ids = ["apui-text-input-1", "apui-text-input-2"]
        self.assertEqual(re.findall(r'id="(apui-text-input-\d+)"', first), expected_ids)
        self.assertEqual(re.findall(r'id="(apui-text-input-\d+)"', second), expected_ids)

    def test_generated_ids_share_document_counter_with_menubar(self):
        output, caught = self.render_with_warnings(
            '{% ui "text_input" label="First" description="Help" %}{% endui %}'
            '{% ui "menubar" aria_label="Nav" %}'
            '{% ui "menubar_section" title="Account" %}'
            '{% ui "menubar_item" href="/profile/" %}Profile{% endui %}'
            "{% endui %}"
            "{% endui %}"
            '{% ui "text_input" label="Second" errorMessage="Required" '
            'validationState="invalid" %}{% endui %}'
        )

        self.assertEqual(caught, [])
        self.assertIn('id="apui-text-input-1"', output)
        self.assertIn('aria-describedby="apui-text-input-2"', output)
        self.assertIn('id="apui-menubar-3"', output)
        self.assertIn('aria-labelledby="apui-menubar-3"', output)
        self.assertIn('id="apui-text-input-4"', output)
        self.assertIn('aria-describedby="apui-text-input-5"', output)

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

    def test_number_input_format_options_are_serialized_for_the_attach_runtime(self):
        output, caught = self.render_with_warnings(
            '{% ui "number_input" label="Price" formatOptions=format_options defaultValue=12.5 %}{% endui %}',
            {"format_options": {"style": "currency", "currency": "AUD"}},
        )
        self.assertEqual(caught, [])
        self.assertIn(
            'data-apui-number-input-format-options="{&quot;currency&quot;:&quot;AUD&quot;,'
            '&quot;style&quot;:&quot;currency&quot;}"',
            output,
        )
        self.assertIn('value="12.5"', output)
        self.assertIn('data-apui-number-input-initial-value="12.5"', output)

    def test_number_input_min_max_step_are_serialized_for_the_attach_runtime(self):
        output, caught = self.render_with_warnings(
            '{% ui "number_input" label="Qty" minValue=1 maxValue=20 step=2 %}{% endui %}'
        )
        self.assertEqual(caught, [])
        self.assertIn('data-apui-number-input-min-value="1"', output)
        self.assertIn('data-apui-number-input-max-value="20"', output)
        self.assertIn('data-apui-number-input-step="2"', output)
        # The visible text input deliberately does not expose native number constraints.
        self.assertNotIn("min=", output)
        self.assertNotIn("max=", output)

    def test_number_input_hidden_input_only_when_name_given(self):
        output_with_name, _ = self.render_with_warnings(
            '{% ui "number_input" label="Qty" name="qty" %}{% endui %}'
        )
        self.assertIn('type="hidden"', output_with_name)
        self.assertIn('name="qty"', output_with_name)
        self.assertIn("data-apui-number-input-value-id=", output_with_name)
        # The visible input must not carry the name so only the hidden input value is submitted
        self.assertEqual(output_with_name.count('name="qty"'), 1)

        output_without_name, _ = self.render_with_warnings('{% ui "number_input" label="Qty" %}{% endui %}')
        self.assertNotIn('type="hidden"', output_without_name)

    def test_number_input_zero_value_renders(self):
        output, _ = self.render_with_warnings(
            '{% ui "number_input" label="Qty" name="qty" value=0 %}{% endui %}'
        )
        self.assertIn('name="qty" value="0"', output)

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
        self.assertNotIn('data-has-addon-after="true"', output)
        self.assertNotIn("TextInputBase_addonAfter", output)

    def test_number_input_step_buttons_disabled_when_input_disabled(self):
        output, _ = self.render_with_warnings(
            '{% ui "number_input" label="Qty" isDisabled=True %}{% endui %}'
        )
        self.assertIn('<button type="button" disabled', output)

    def test_number_input_step_buttons_disabled_when_input_readonly(self):
        output, _ = self.render_with_warnings(
            '{% ui "number_input" label="Qty" isReadOnly=True %}{% endui %}'
        )
        self.assertEqual(output.count('<button type="button" disabled'), 2)

    def test_number_input_validation_icon_is_mutually_exclusive_with_step_buttons(self):
        with_steps, _ = self.render_with_warnings(
            '{% ui "number_input" label="Qty" validationState="invalid" %}{% endui %}'
        )
        self.assertIn('data-invalid="true"', with_steps)
        self.assertIn('data-direction="up"', with_steps)
        self.assertNotIn("TextInputBase_validationIcon", with_steps)
        self.assertEqual(with_steps.count("<svg"), 2)

        without_steps_invalid, _ = self.render_with_warnings(
            '{% ui "number_input" label="Qty" validationState="invalid" hideStepButtons=True %}{% endui %}'
        )
        self.assertNotIn("data-direction", without_steps_invalid)
        self.assertIn("TextInputBase_validationIcon", without_steps_invalid)
        self.assertIn('d="M12 8V12M12 16H12.01', without_steps_invalid)
        self.assertEqual(without_steps_invalid.count("<svg"), 1)

        without_steps_valid, _ = self.render_with_warnings(
            '{% ui "number_input" label="Qty" validationState="valid" hideStepButtons=True %}{% endui %}'
        )
        self.assertIn('data-valid="true"', without_steps_valid)
        self.assertIn("TextInputBase_validationIcon", without_steps_valid)
        self.assertIn('d="M20 6L9 17L4 12"', without_steps_valid)
        self.assertEqual(without_steps_valid.count("<svg"), 1)

    def test_number_input_validation_icon_remains_hidden_when_disabled(self):
        output, _ = self.render_with_warnings(
            '{% ui "number_input" label="Qty" validationState="invalid" hideStepButtons=True '
            "isDisabled=True %}{% endui %}"
        )
        self.assertNotIn("TextInputBase_validationIcon", output)
        self.assertEqual(output.count("<svg"), 0)

    def test_number_input_sm_and_md_size_contract(self):
        output, _ = self.render_with_warnings(
            '{% ui "number_input" label="Small" inputSize="sm" %}{% endui %}'
            '{% ui "number_input" label="Medium" inputSize="md" %}{% endui %}'
        )
        self.assertIn("TextInputBase_sizes_sm", output)
        self.assertIn("TextInputBase_sizes_md", output)
        self.assertIn('data-size="sm"', output)
        self.assertIn('data-size="md"', output)

    def test_number_input_is_marked_for_collected_external_auto_attachment(self):
        output, _ = self.render_with_warnings(
            '{% ui "number_input" label="Qty" name="qty" defaultValue=5 %}{% endui %}'
        )
        self.assertIn('data-apui-attach="number-input"', output)
        self.assertNotIn("<script", output)
        value_input_id = re.search(r'data-apui-number-input-value-id="([^"]+)"', output).group(1)
        self.assertIn(f'id="{value_input_id}"', output)

    def test_number_input_collected_assets_do_not_emit_detached_icon_images(self):
        with self.setup_render_context():
            output = self.render_ui_document(
                '{% ui "number_input" label="Qty" validationState="invalid" %}{% endui %}'
            )

        # Only the two inline step chevrons render. The validation/build dependency SVGs must not
        # be emitted at the collected-assets insertion point.
        self.assertEqual(output.count("<svg"), 2)
        self.assertNotIn("<img", output)
        self.assertNotIn("TextInputBase_validationIcon", output)
        self.assertIn("NumberInput.auto.ts", output)

    def test_number_input_collected_assets_keep_hide_step_validation_icon_in_place(self):
        with self.setup_render_context():
            output = self.render_ui_document(
                '{% ui "number_input" label="Qty" validationState="valid" hideStepButtons=True %}{% endui %}'
            )

        self.assertEqual(output.count("<svg"), 1)
        self.assertNotIn("<img", output)
        self.assertIn("TextInputBase_validationIcon", output)

    def test_bulk_props_accept_html_attribute_names(self):
        # Simulates a Django form widget template passing `props=widget.attrs`
        output, caught = self.render_with_warnings(
            '{% ui "text_input" props=attrs name="email" %}{% endui %}',
            {
                "attrs": {
                    "id": "id_email",
                    "maxlength": "100",
                    "class": "widget-class",
                    "required": True,
                    "readonly": True,
                    "autofocus": True,
                    "aria-describedby": "external-help",
                    "label": "Email",
                }
            },
        )
        self.assertEqual(caught, [])
        self.assertIn('id="id_email"', output)
        self.assertIn('for="id_email"', output)
        self.assertIn('maxlength="100"', output)
        self.assertIn("LabeledInput_labeledInput_labelPosition_top widget-class", output)
        self.assertIn('aria-required="true"', output)
        self.assertIn('data-required="true"', output)
        self.assertIn(" readonly", output)
        self.assertIn('data-readonly="true"', output)
        self.assertIn(" autofocus", output)
        self.assertIn('aria-describedby="external-help"', output)

    def test_bulk_props_disabled_does_not_warn(self):
        # widget.attrs expresses disabled state with the HTML attribute name; unlike an inline
        # disabled= kwarg this should not trigger the isDisabled alias warning
        output, caught = self.render_with_warnings(
            '{% ui "text_input" label="Email" props=attrs %}{% endui %}',
            {"attrs": {"disabled": True}},
        )
        self.assertEqual(caught, [])
        self.assertIn('data-disabled="true"', output)
        self.assertIn(" disabled", output)

    def test_bulk_props_take_precedence_except_class_names_merge(self):
        output, _ = self.render_with_warnings(
            '{% ui "text_input" label="Inline label" className="inline-class" props=attrs %}{% endui %}',
            {"attrs": {"label": "Dict label", "class": "dict-class"}},
        )
        self.assertIn("Dict label", output)
        self.assertNotIn("Inline label", output)
        self.assertIn("inline-class dict-class", output)

    def test_bulk_props_non_dict_warns_and_is_ignored(self):
        output, caught = self.render_with_warnings(
            '{% ui "text_input" label="Email" props="not-a-dict" %}{% endui %}'
        )
        self.assertTrue(any(message.startswith("'props' must be a dict of props") for message in caught))
        self.assertIn("Email", output)

    def test_merge_props_filter_is_available_from_ui_library(self):
        output, caught = self.render_with_warnings(
            '{% ui "text_input" props=attrs|merge_props:extra %}{% endui %}',
            {"attrs": {"id": "id_field"}, "extra": {"label": "Merged label"}},
        )
        self.assertEqual(caught, [])
        self.assertIn("Merged label", output)
        self.assertIn('id="id_field"', output)

    def test_lazy_translation_values_are_treated_as_strings(self):
        # Django form field labels are commonly lazy translation proxies (e.g.
        # AuthenticationForm's password field); these must render like plain strings
        output, caught = self.render_with_warnings(
            '{% ui "text_input" props=attrs %}{% endui %}',
            {
                "attrs": {
                    "id": "id_password",
                    "label": gettext_lazy("Password"),
                    "placeholder": gettext_lazy("Enter password"),
                    "description": gettext_lazy("Keep it secret"),
                }
            },
        )
        self.assertEqual(caught, [])
        self.assertIn(">Password</label>", output)
        self.assertIn('for="id_password"', output)
        self.assertIn('placeholder="Enter password"', output)
        self.assertIn(">Keep it secret</div>", output)

    def test_decimal_values_render_on_number_input(self):
        output, caught = self.render_with_warnings(
            '{% ui "number_input" label="Price" name="price" defaultValue=value %}{% endui %}',
            {"value": Decimal("12.50")},
        )
        self.assertEqual(caught, [])
        self.assertIn('value="12.50"', output)
        self.assertIn('name="price" value="12.50"', output)

    def test_none_valued_props_are_treated_as_unset(self):
        output, caught = self.render_with_warnings(
            '{% ui "text_input" label="Email" placeholder=missing_value labelAlign=missing_value %}{% endui %}',
            {"missing_value": None},
        )
        self.assertEqual(caught, [])
        self.assertNotIn("placeholder", output)
        self.assertNotIn("data-label-align", output)
