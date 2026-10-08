import path from "node:path";

export const component = "text_input";
export const class_prefixes = [
  "LabeledInput",
  "TextInputBase",
  "focusRing",
  "Label",
  "FormSection",
  "Icon",
];
// The LabeledInput recipe base class is emitted alongside its variant classes by both the JS
// and Python renderers, so exempt it from the "drop parent when child token exists" rule.
export const keep_class_tokens = ["LabeledInput_labeledInput"];

export const stylesheets = [
  "@alliancesoftware/ui/components/text-input/TextInputBase.css.ts",
  "@alliancesoftware/ui/components/form/LabeledInput.css.ts",
  "@alliancesoftware/ui/components/form/Label.css.ts",
  "@alliancesoftware/ui/components/form/FormSection.css.ts",
  "@alliancesoftware/ui/styles/base/focusRing.css.ts",
  "@alliancesoftware/icons/Icon.css.ts",
];

export async function loadComponents({ uiPackageDir, importDefault }) {
  return {
    TextInput: await importDefault(
      path.join(uiPackageDir, "components/text-input/TextInput.tsx")
    ),
  };
}

export function normalize(root, testCase, helpers) {
  helpers.normalizeInputComponent(root, component);
}

export const cases = [
  {
    name: "default",
    template: '{% ui "text_input" label="Email" %}',
    buildElement({ React, components }) {
      const { TextInput } = components;
      return React.createElement(TextInput, { label: "Email" });
    },
    meta: {},
  },
  {
    name: "name_type_placeholder_default_value",
    template:
      '{% ui "text_input" label="Email" name="email" type="email" placeholder="name@example.com" defaultValue="jane@example.com" %}',
    buildElement({ React, components }) {
      const { TextInput } = components;
      return React.createElement(TextInput, {
        label: "Email",
        name: "email",
        type: "email",
        placeholder: "name@example.com",
        defaultValue: "jane@example.com",
      });
    },
    meta: {},
  },
  {
    name: "description",
    template:
      '{% ui "text_input" label="Name" description="Shown on your profile" %}',
    buildElement({ React, components }) {
      const { TextInput } = components;
      return React.createElement(TextInput, {
        label: "Name",
        description: "Shown on your profile",
      });
    },
    meta: {},
  },
  {
    name: "invalid_with_error_message",
    template:
      '{% ui "text_input" label="Email" validationState="invalid" errorMessage="Enter a valid email" %}',
    buildElement({ React, components }) {
      const { TextInput } = components;
      return React.createElement(TextInput, {
        label: "Email",
        validationState: "invalid",
        errorMessage: "Enter a valid email",
      });
    },
    meta: {},
  },
  {
    name: "invalid_error_replaces_description",
    template:
      '{% ui "text_input" label="Email" validationState="invalid" errorMessage="Enter a valid email" description="Your work email" %}',
    buildElement({ React, components }) {
      const { TextInput } = components;
      return React.createElement(TextInput, {
        label: "Email",
        validationState: "invalid",
        errorMessage: "Enter a valid email",
        description: "Your work email",
      });
    },
    meta: {},
  },
  {
    name: "valid",
    template: '{% ui "text_input" label="Email" validationState="valid" %}',
    buildElement({ React, components }) {
      const { TextInput } = components;
      return React.createElement(TextInput, {
        label: "Email",
        validationState: "valid",
      });
    },
    meta: {},
  },
  {
    name: "disabled",
    template: '{% ui "text_input" label="Email" isDisabled=True %}',
    buildElement({ React, components }) {
      const { TextInput } = components;
      return React.createElement(TextInput, {
        label: "Email",
        isDisabled: true,
      });
    },
    meta: {},
  },
  {
    name: "readonly",
    template:
      '{% ui "text_input" label="Code" value="ABC123" isReadOnly=True %}',
    buildElement({ React, components }) {
      const { TextInput } = components;
      return React.createElement(TextInput, {
        label: "Code",
        value: "ABC123",
        isReadOnly: true,
      });
    },
    meta: {},
  },
  {
    name: "required",
    template: '{% ui "text_input" label="Email" isRequired=True %}',
    buildElement({ React, components }) {
      const { TextInput } = components;
      return React.createElement(TextInput, {
        label: "Email",
        isRequired: true,
      });
    },
    meta: {},
  },
  {
    name: "label_position_side_align_end",
    template:
      '{% ui "text_input" label="Email" labelPosition="side" labelAlign="end" %}',
    buildElement({ React, components }) {
      const { TextInput } = components;
      return React.createElement(TextInput, {
        label: "Email",
        labelPosition: "side",
        labelAlign: "end",
      });
    },
    meta: {},
  },
  {
    name: "input_size_md",
    template: '{% ui "text_input" label="Email" inputSize="md" %}',
    buildElement({ React, components }) {
      const { TextInput } = components;
      return React.createElement(TextInput, {
        label: "Email",
        inputSize: "md",
      });
    },
    meta: {},
  },
  {
    name: "addon_before_and_after",
    template:
      '{% ui "text_input" label="Website" addonBefore="https://" addonAfter=".com" %}',
    buildElement({ React, components }) {
      const { TextInput } = components;
      return React.createElement(TextInput, {
        label: "Website",
        addonBefore: "https://",
        addonAfter: ".com",
      });
    },
    meta: {},
  },
  {
    name: "custom_class_names",
    template:
      '{% ui "text_input" label="Email" className="custom-root" inputClassName="custom-input" %}',
    buildElement({ React, components }) {
      const { TextInput } = components;
      return React.createElement(TextInput, {
        label: "Email",
        className: "custom-root",
        inputClassName: "custom-input",
      });
    },
    meta: {},
  },
  {
    name: "caller_id_and_aria_describedby",
    template:
      '{% ui "text_input" label="Email" id="my-id" aria_describedby="external-desc" description="Some description" %}',
    buildElement({ React, components }) {
      const { TextInput } = components;
      return React.createElement(TextInput, {
        label: "Email",
        id: "my-id",
        "aria-describedby": "external-desc",
        description: "Some description",
      });
    },
    meta: {},
  },
];
