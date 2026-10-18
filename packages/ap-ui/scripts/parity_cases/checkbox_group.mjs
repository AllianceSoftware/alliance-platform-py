import path from "node:path";

// The checkbox group and the checkboxes in it. A case's `meta.context` holds the template context the
// Python parity test renders its template with, such as the list of checked values.
export const component = "checkbox_group";
export const class_prefixes = [
  "LabeledInput",
  "Label",
  "FormSection",
  "CheckboxGroup",
  "Checkbox",
  "focusRing",
];

export const stylesheets = [
  "@alliancesoftware/ui/components/form/LabeledInput.css.ts",
  "@alliancesoftware/ui/components/form/Label.css.ts",
  "@alliancesoftware/ui/components/form/FormSection.css.ts",
  "@alliancesoftware/ui/components/checkbox/CheckboxGroup.css.ts",
  "@alliancesoftware/ui/components/checkbox/Checkbox.css.ts",
];

export async function loadComponents({ uiPackageDir, importDefault }) {
  return {
    CheckboxGroup: await importDefault(
      path.join(uiPackageDir, "components/checkbox/CheckboxGroup.tsx")
    ),
    Checkbox: await importDefault(
      path.join(uiPackageDir, "components/checkbox/Checkbox.tsx")
    ),
  };
}

export function normalize(root, testCase, helpers) {
  helpers.normalizeChoiceGroup(root, component);
}

const PETS = [
  ["cat", "Cat"],
  ["dog", "Dog"],
];

function checkboxGroupCase({
  name,
  templateProps = "",
  props = {},
  context = {},
  checkboxes = PETS.map(([value, label]) => ({ value, label })),
}) {
  return {
    name,
    template:
      `{% ui "checkbox_group" label="Pets" name="pets"${templateProps} %}` +
      checkboxes
        .map(
          ({ value, label, templateProps: checkboxProps = "" }) =>
            `{% ui "checkbox"${value === undefined ? "" : ` value="${value}"`}${checkboxProps} %}${label}{% endui %}`
        )
        .join("") +
      "{% endui %}",
    buildElement({ React, components }) {
      return React.createElement(
        components.CheckboxGroup,
        { label: "Pets", name: "pets", ...props },
        ...checkboxes.map(({ value, label, props: checkboxProps = {} }) =>
          React.createElement(
            components.Checkbox,
            { key: value ?? label, value, ...checkboxProps },
            label
          )
        )
      );
    },
    meta: { context },
  };
}

export const cases = [
  checkboxGroupCase({ name: "default" }),
  checkboxGroupCase({
    name: "default_value",
    templateProps: " default_value=checked",
    props: { defaultValue: ["dog"] },
    context: { checked: ["dog"] },
  }),
  checkboxGroupCase({
    // A string checks that one value in a template; React takes a list
    name: "value_string",
    templateProps: ' value="cat"',
    props: { value: ["cat"] },
  }),
  checkboxGroupCase({
    name: "description",
    templateProps: ' description="Choose any"',
    props: { description: "Choose any" },
  }),
  checkboxGroupCase({
    name: "invalid_with_error_message",
    templateProps:
      ' description="Choose any" is_invalid=True error_message="Choose a pet"',
    props: {
      description: "Choose any",
      isInvalid: true,
      errorMessage: "Choose a pet",
    },
  }),
  checkboxGroupCase({
    // The error message renders, but the group and its checkboxes stay valid
    name: "has_invalid_children",
    templateProps: ' has_invalid_children=True error_message="Check the pets"',
    props: { hasInvalidChildren: true, errorMessage: "Check the pets" },
  }),
  checkboxGroupCase({
    name: "disabled_read_only_and_required",
    templateProps: " is_disabled=True is_read_only=True is_required=True",
    props: { isDisabled: true, isReadOnly: true, isRequired: true },
  }),
  checkboxGroupCase({
    name: "disabled_checkbox",
    checkboxes: [
      { value: "cat", label: "Cat" },
      {
        value: "dog",
        label: "Dog",
        templateProps: " is_disabled=True",
        props: { isDisabled: true },
      },
    ],
  }),
  checkboxGroupCase({
    name: "horizontal_md",
    templateProps: ' orientation="horizontal" input_size="md"',
    props: { orientation: "horizontal", inputSize: "md" },
  }),
  checkboxGroupCase({
    name: "label_position_side",
    templateProps:
      ' label_position="side" label_align="end" description="Choose any"',
    props: {
      labelPosition: "side",
      labelAlign: "end",
      description: "Choose any",
    },
  }),
  checkboxGroupCase({
    // The label, help text and error message are named after a given id
    name: "id_with_error_message",
    templateProps:
      ' id="id_pets" description="Choose any" validation_state="invalid" error_message="Choose a pet"',
    props: {
      id: "id_pets",
      description: "Choose any",
      validationState: "invalid",
      errorMessage: "Choose a pet",
    },
  }),
  checkboxGroupCase({
    name: "class_name",
    templateProps: ' class="pet-picker"',
    props: { className: "pet-picker" },
  }),
  checkboxGroupCase({
    // React's Checkbox warns about a checkbox in a group without a value; the static one reports it
    name: "checkbox_without_value",
    checkboxes: [{ value: "cat", label: "Cat" }, { label: "Dog" }],
  }),
];
