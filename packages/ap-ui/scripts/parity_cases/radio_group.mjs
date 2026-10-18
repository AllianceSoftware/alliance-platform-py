import path from "node:path";
import { pathToFileURL } from "node:url";

// The radio group and the radios in it
export const component = "radio_group";
export const class_prefixes = [
  "LabeledInput",
  "Label",
  "FormSection",
  "RadioGroup",
  "Checkbox",
  "focusRing",
];

export const stylesheets = [
  "@alliancesoftware/ui/components/form/LabeledInput.css.ts",
  "@alliancesoftware/ui/components/form/Label.css.ts",
  "@alliancesoftware/ui/components/form/FormSection.css.ts",
  "@alliancesoftware/ui/components/radio-group/RadioGroup.css.ts",
];

export async function loadComponents({ uiPackageDir, importDefault }) {
  const radioGroupPath = path.join(
    uiPackageDir,
    "components/radio-group/RadioGroup.tsx"
  );
  const radioGroupModule = await import(pathToFileURL(radioGroupPath).href);
  return {
    RadioGroup: await importDefault(radioGroupPath),
    Radio: radioGroupModule.Radio,
  };
}

export function normalize(root, testCase, helpers) {
  helpers.normalizeChoiceGroup(root, component);
}

const COLOURS = [
  ["red", "Red"],
  ["green", "Green"],
  ["blue", "Blue"],
];

function radioGroupCase({
  name,
  templateProps = "",
  props = {},
  radios = COLOURS.map(([value, label]) => ({ value, label })),
  groupName = "colour",
}) {
  const nameProp = groupName ? ` name="${groupName}"` : "";
  return {
    name,
    template:
      `{% ui "radio_group" label="Colour"${nameProp}${templateProps} %}` +
      radios
        .map(
          ({ value, label, templateProps: radioProps = "" }) =>
            `{% ui "radio" value="${value}"${radioProps} %}${label}{% endui %}`
        )
        .join("") +
      "{% endui %}",
    buildElement({ React, components }) {
      return React.createElement(
        components.RadioGroup,
        {
          label: "Colour",
          ...(groupName ? { name: groupName } : {}),
          ...props,
        },
        ...radios.map(({ value, label, props: radioProps = {} }) =>
          React.createElement(
            components.Radio,
            { key: value, value, ...radioProps },
            label
          )
        )
      );
    },
    meta: {},
  };
}

export const cases = [
  radioGroupCase({ name: "default" }),
  radioGroupCase({
    name: "default_value",
    templateProps: ' default_value="green"',
    props: { defaultValue: "green" },
  }),
  radioGroupCase({
    name: "value",
    templateProps: ' value="blue"',
    props: { value: "blue" },
  }),
  radioGroupCase({
    name: "description",
    templateProps: ' description="Pick one" default_value="red"',
    props: { description: "Pick one", defaultValue: "red" },
  }),
  radioGroupCase({
    name: "invalid_with_error_message",
    templateProps:
      ' description="Pick one" is_invalid=True error_message="Pick a colour"',
    props: {
      description: "Pick one",
      isInvalid: true,
      errorMessage: "Pick a colour",
    },
  }),
  radioGroupCase({
    // {% form_input %} passes validationState; react-aria reads it as RadioGroup passes it on
    name: "validation_state_invalid",
    templateProps: ' validation_state="invalid" error_message="Pick a colour"',
    props: { validationState: "invalid", errorMessage: "Pick a colour" },
  }),
  radioGroupCase({
    name: "disabled",
    templateProps: ' is_disabled=True default_value="red"',
    props: { isDisabled: true, defaultValue: "red" },
  }),
  radioGroupCase({
    name: "disabled_radio",
    radios: [
      { value: "red", label: "Red" },
      {
        value: "green",
        label: "Green",
        templateProps: " is_disabled=True",
        props: { isDisabled: true },
      },
      { value: "blue", label: "Blue" },
    ],
  }),
  radioGroupCase({
    name: "read_only_and_required",
    templateProps: ' is_read_only=True is_required=True default_value="red"',
    props: { isReadOnly: true, isRequired: true, defaultValue: "red" },
  }),
  radioGroupCase({
    name: "horizontal_md",
    templateProps: ' orientation="horizontal" input_size="md"',
    props: { orientation: "horizontal", inputSize: "md" },
  }),
  radioGroupCase({
    name: "label_position_side",
    templateProps:
      ' label_position="side" label_align="end" description="Pick one"',
    props: {
      labelPosition: "side",
      labelAlign: "end",
      description: "Pick one",
    },
  }),
  radioGroupCase({
    // The label, help text and error message are named after a given id, and each radio takes the
    // id Django gives its option
    name: "ids",
    templateProps:
      ' id="id_colour" description="Pick one" validation_state="invalid" error_message="Pick a colour"',
    props: {
      id: "id_colour",
      description: "Pick one",
      validationState: "invalid",
      errorMessage: "Pick a colour",
    },
    radios: COLOURS.map(([value, label], index) => ({
      value,
      label,
      templateProps: ` id="id_colour_${index}"`,
      props: { id: `id_colour_${index}` },
    })),
  }),
  radioGroupCase({
    name: "class_name",
    templateProps: ' class="colour-picker"',
    props: { className: "colour-picker" },
  }),
  radioGroupCase({
    // Radios need a name to form a group, so one is generated, as react-aria does
    name: "generated_name",
    groupName: null,
  }),
];
