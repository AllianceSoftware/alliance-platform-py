from __future__ import annotations

from alliance_platform.frontend.renderable_content import RenderableContent
from alliance_platform.ui.html_components.diagnostics import StaticComponentContractError
import django
from django import forms
from django.template import Origin

from tests.parity.base import HtmlUIParityTestCase
from tests.test_utils import override_ap_ui_settings

MISSING_INPUT_ID = (
    "'labeled_input' has a label but no 'input_id', so the label is not associated with a control: "
    "pass the id of the control it wraps"
)


class ColourForm(forms.Form):
    colour = forms.ChoiceField(
        label="Colour",
        choices=[("red", "Red"), ("blue", "Blue")],
        help_text="Pick one",
    )


class UILabeledInputTestCase(HtmlUIParityTestCase):
    def render_with_warnings(self, template_body: str, context_kwargs=None):
        with self.setup_render_context():
            with self.capture_diagnostics() as diagnostics:
                output = self.render_ui_template(template_body, context_kwargs)
        return output, diagnostics

    def test_wraps_the_children_in_the_label_and_help_text(self):
        output, caught = self.render_with_warnings(
            '{% ui "labeled_input" label="Colour" input_id="id_colour" description="Pick one" %}'
            '<select id="id_colour" name="colour"></select>'
            "{% endui %}"
        )

        self.assertEqual(caught, [])
        self.assertEqual(
            output,
            # LabeledInput takes labelAlign="start" from the default form layout
            '<div data-labeledinput="1" data-apui="labeled-input" data-label-position="top" '
            'data-label-align="start" data-input-size="sm" class="LabeledInput_labeledInput">'
            '<label data-apui="label" data-label-align="start" class="Label_label LabeledInput_label" '
            'for="id_colour">Colour</label>'
            '<div class="LabeledInput_input"><select id="id_colour" name="colour"></select></div>'
            '<div class="LabeledInput_helpText" id="id_colour_helptext">Pick one</div>'
            "</div>",
        )

    def test_error_message_replaces_the_description_and_is_named_after_the_input_id(self):
        output, caught = self.render_with_warnings(
            '{% ui "labeled_input" label="Colour" input_id="id_colour" description="Pick one" '
            'error_message="Select a colour" is_invalid=True %}<select id="id_colour"></select>{% endui %}'
        )

        self.assertEqual(caught, [])
        self.assertIn('class="LabeledInput_labeledInput" data-invalid="true"', output)
        self.assertIn('<div class="LabeledInput_helpText" id="id_colour_error">Select a colour</div>', output)
        self.assertNotIn("Pick one", output)
        self.assertNotIn("_helptext", output)

    def test_children_are_not_changed(self):
        # The control is the children's markup: no aria-describedby or id is added to it
        output, _ = self.render_with_warnings(
            '{% ui "labeled_input" label="Colour" input_id="id_colour" description="Pick one" %}'
            '<select id="id_colour"></select>{% endui %}'
        )

        self.assertIn('<div class="LabeledInput_input"><select id="id_colour"></select></div>', output)
        self.assertNotIn("aria-describedby", output)

    def test_validation_state_invalid_sets_is_invalid(self):
        invalid, caught = self.render_with_warnings(
            '{% ui "labeled_input" label="Colour" input_id="id_colour" validation_state="invalid" '
            'error_message="Select a colour" %}<select id="id_colour"></select>{% endui %}'
        )
        valid, _ = self.render_with_warnings(
            '{% ui "labeled_input" label="Colour" input_id="id_colour" validation_state="valid" '
            'error_message="Select a colour" %}<select id="id_colour"></select>{% endui %}'
        )

        self.assertEqual(caught, [])
        self.assertIn('data-invalid="true"', invalid)
        self.assertIn('id="id_colour_error">Select a colour</div>', invalid)
        # A valid state has no static presentation without a control the renderer owns
        self.assertNotIn("data-invalid", valid)
        self.assertNotIn("data-valid", valid)
        self.assertNotIn("Select a colour", valid)

    def test_state_props_set_root_data_attributes(self):
        output, caught = self.render_with_warnings(
            '{% ui "labeled_input" label="Colour" input_id="id_colour" is_required=True is_disabled=True '
            'is_read_only=True %}<select id="id_colour"></select>{% endui %}'
        )

        self.assertEqual(caught, [])
        # Unlike the inputs, LabeledInput marks the root disabled itself
        self.assertIn(
            'class="LabeledInput_labeledInput" data-disabled="true" data-required="true" data-readonly="true"',
            output,
        )
        self.assertIn(
            'Colour<span aria-hidden="true" class="Label_requiredIndicator">*</span></label>', output
        )

    def test_layout_props_set_root_data_attributes_and_classes(self):
        output, caught = self.render_with_warnings(
            '{% ui "labeled_input" label="Colour" input_id="id_colour" label_align="end" input_size="md" '
            'class="custom" style="margin: 0" %}<select id="id_colour"></select>{% endui %}'
        )

        self.assertEqual(caught, [])
        self.assertIn(
            'data-label-position="top" data-label-align="end" data-input-size="md" '
            'class="LabeledInput_labeledInput custom" style="margin: 0"',
            output,
        )
        self.assertIn('<label data-apui="label" data-label-align="end"', output)

    def test_side_layout(self):
        labelled, caught = self.render_with_warnings(
            '{% ui "labeled_input" label="Colour" input_id="id_colour" label_position="side" '
            'description="Pick one" %}<select id="id_colour"></select>{% endui %}'
        )
        unlabelled, _ = self.render_with_warnings(
            '{% ui "labeled_input" label_position="side" %}<select aria-label="Colour"></select>{% endui %}'
        )

        self.assertEqual(caught, [])
        self.assertIn(
            'for="id_colour">Colour</label><div class="FormSection_inputHelpSideWrapper">'
            '<div class="LabeledInput_input"><select id="id_colour"></select></div>'
            '<div class="LabeledInput_helpText" id="id_colour_helptext">Pick one</div></div>',
            labelled,
        )
        # Without a label the side layout keeps a placeholder cell
        self.assertIn(
            '<div class="FormSection_sideLabelPlaceholder"></div><div class="FormSection_inputHelpSideWrapper">',
            unlabelled,
        )

    def test_label_without_input_id_is_reported_and_has_no_for(self):
        output, caught = self.render_with_warnings(
            '{% ui "labeled_input" label="Colour" description="Pick one" error_message="Required" '
            "is_invalid=False %}<select></select>{% endui %}"
        )

        self.assertEqual(caught, [MISSING_INPUT_ID])
        self.assertIn(
            '<label data-apui="label" data-label-align="start" class="Label_label LabeledInput_label">Colour</label>',
            output,
        )
        # Help text falls back to a generated id
        self.assertIn('<div class="LabeledInput_helpText" id="apui-labeled-input-1">Pick one</div>', output)

    @override_ap_ui_settings(STATIC_COMPONENT_STRICT=True)
    def test_label_without_input_id_is_a_contract_problem(self):
        with self.assertRaisesMessage(StaticComponentContractError, MISSING_INPUT_ID):
            self.render_with_warnings('{% ui "labeled_input" label="Colour" %}<select></select>{% endui %}')

    def test_help_text_and_error_without_input_id_get_generated_ids(self):
        output, caught = self.render_with_warnings(
            '{% ui "labeled_input" description="Pick one" %}<select aria-label="Colour"></select>{% endui %}'
            '{% ui "labeled_input" error_message="Required" is_invalid=True %}'
            '<select aria-label="Size"></select>{% endui %}'
        )

        self.assertEqual(caught, [])
        self.assertIn('id="apui-labeled-input-1">Pick one</div>', output)
        self.assertIn('id="apui-labeled-input-2">Required</div>', output)

    def test_description_accepts_renderable_content(self):
        output, caught = self.render_with_warnings(
            '{% ui "labeled_input" label="Colour" input_id="id_colour" description=description %}'
            '<select id="id_colour"></select>{% endui %}',
            {"description": RenderableContent.from_html("Pick <strong>one</strong>", Origin("test"))},
        )

        self.assertEqual(caught, [])
        self.assertIn('id="id_colour_helptext">Pick <strong>one</strong></div>', output)

    def test_props_of_the_control_are_accepted_but_not_rendered(self):
        # A widget template can pass extra_widget_props whole; {% form_input %} adds autoFocus
        output, caught = self.render_with_warnings(
            '{% ui "labeled_input" props=extra input_id="id_colour" %}<select id="id_colour"></select>{% endui %}',
            {
                "extra": {
                    "label": "Colour",
                    "auto_focus": True,
                    "title": "Colour",
                    "data-testid": "colour",
                    "aria-label": "Colour",
                }
            },
        )

        self.assertEqual(caught, [])
        for attribute in ("autofocus", "title=", "data-testid", "aria-label"):
            with self.subTest(attribute=attribute):
                self.assertNotIn(attribute, output)

    def test_react_only_props_are_refused(self):
        props = ("labelProps", "descriptionProps", "errorMessageProps", "containerProps", "labelRef")
        output, caught = self.render_with_warnings(
            '{% ui "labeled_input" label="Colour" input_id="id_colour" label_props=value '
            "description_props=value error_message_props=value container_props=value label_ref=value %}"
            '<select id="id_colour"></select>{% endui %}',
            {"value": {"id": "x"}},
        )

        self.assertEqual(
            caught,
            [
                f"Prop '{prop}' will be ignored: React-only props are not supported by static labeled inputs; "
                "use {% LabeledInput %} instead"
                for prop in props
            ],
        )
        self.assertNotIn('id="x"', output)

    def test_unknown_props_and_event_handlers_are_reported(self):
        _, caught = self.render_with_warnings(
            '{% ui "labeled_input" label="Colour" input_id="id_colour" addon_before="$" on_change="go()" %}'
            '<select id="id_colour"></select>{% endui %}'
        )

        self.assertEqual(
            caught,
            [
                "Prop 'addonBefore' is not a supported 'labeled_input' prop and will be ignored",
                "Prop 'onChange' will be ignored: event handlers are not supported by static labeled inputs; "
                "use {% LabeledInput %} instead",
            ],
        )

    def test_wraps_a_django_widget(self):
        form = ColourForm()
        output, caught = self.render_with_warnings(
            '{% ui "labeled_input" label=field.label input_id=field.auto_id description=field.help_text %}'
            "{{ field }}{% endui %}",
            {"field": form["colour"]},
        )

        self.assertEqual(caught, [])
        self.assertIn('for="id_colour">Colour</label>', output)
        self.assertIn('<div class="LabeledInput_helpText" id="id_colour_helptext">Pick one</div>', output)
        if django.VERSION >= (5, 0):
            # Django links the widget to the help text by the same id
            self.assertRegex(output, r'<select name="colour"[^>]* aria-describedby="id_colour_helptext"')

    def test_resources_are_registered(self):
        with self.setup_render_context() as asset_context:
            self.render_ui_template(
                '{% ui "labeled_input" label="Colour" input_id="id_colour" %}<select id="id_colour"></select>'
                "{% endui %}"
            )
            resource_paths = [str(resource.path) for resource in asset_context.get_resources_for_bundling()]

        self.assertEqual(
            sorted(path.rsplit("/", 1)[-1] for path in resource_paths),
            ["FormSection.css.ts", "Label.css.ts", "LabeledInput.css.ts"],
        )
