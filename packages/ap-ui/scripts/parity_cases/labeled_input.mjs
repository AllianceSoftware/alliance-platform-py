import path from "node:path";

export const component = "labeled_input";
export const class_prefixes = ["LabeledInput", "Label", "FormSection"];

export const stylesheets = [
  "@alliancesoftware/ui/components/form/LabeledInput.css.ts",
  "@alliancesoftware/ui/components/form/Label.css.ts",
  "@alliancesoftware/ui/components/form/FormSection.css.ts",
];

export async function loadComponents({ uiPackageDir, importDefault }) {
  return {
    LabeledInput: await importDefault(
      path.join(uiPackageDir, "components/form/LabeledInput.tsx")
    ),
  };
}

// LabeledInput generates no ids: each case passes it the label `for` and the description and error
// message ids the static renderer derives from `input_id`, so there is nothing to normalise.
export function normalize() {}

const INPUT_ID = "email";

function labeledInputCase({ name, templateProps, props }) {
  return {
    name,
    // The child is written as the generator serialises void elements
    template: `{% ui "labeled_input" input_id="${INPUT_ID}"${templateProps} %}<input id="${INPUT_ID}" name="email"/>{% endui %}`,
    buildElement({ React, components }) {
      return React.createElement(
        components.LabeledInput,
        {
          labelProps: { htmlFor: INPUT_ID },
          descriptionProps: { id: `${INPUT_ID}_helptext` },
          errorMessageProps: { id: `${INPUT_ID}_error` },
          ...props,
        },
        React.createElement("input", { id: INPUT_ID, name: "email" })
      );
    },
    meta: {},
  };
}

export const cases = [
  labeledInputCase({
    name: "label",
    templateProps: ' label="Email"',
    props: { label: "Email" },
  }),
  labeledInputCase({
    name: "description",
    templateProps: ' label="Email" description="Your work email"',
    props: { label: "Email", description: "Your work email" },
  }),
  labeledInputCase({
    // {% LabeledInput %} turns validationState="invalid" into isInvalid as the static renderer does
    name: "error_message",
    templateProps:
      ' label="Email" description="Your work email" validation_state="invalid" error_message="Enter a valid email"',
    props: {
      label: "Email",
      description: "Your work email",
      isInvalid: true,
      errorMessage: "Enter a valid email",
    },
  }),
  labeledInputCase({
    name: "side_layout",
    templateProps:
      ' label="Email" label_position="side" label_align="end" description="Your work email"',
    props: {
      label: "Email",
      labelPosition: "side",
      labelAlign: "end",
      description: "Your work email",
    },
  }),
  labeledInputCase({
    name: "required_disabled_readonly",
    templateProps:
      ' label="Email" is_required=True is_disabled=True is_read_only=True',
    props: {
      label: "Email",
      isRequired: true,
      isDisabled: true,
      isReadOnly: true,
    },
  }),
];
