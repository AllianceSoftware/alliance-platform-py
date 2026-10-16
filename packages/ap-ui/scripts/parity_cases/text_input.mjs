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
    // The wrapper React gives a text addon; the static renderer gives a string the same span
    Text: await importDefault(path.join(uiPackageDir, "components/layout/Text.tsx")),
    // An icon the static tests copy to tests/fixtures/icons/static-svg
    CheckOutlined: await importDefault(
      path.join(uiPackageDir, "../icons/outlined/CheckOutlined.tsx")
    ),
  };
}

export function normalize(root, testCase, helpers) {
  // React's Icon only gets data-apui-slot from a parent's slot context, which an addon does not
  // provide; the static icon an addon holds always marks its root (see icon.mjs)
  for (const icon of root.querySelectorAll(
    '[class*="TextInputBase_addon"] > [role="img"]'
  )) {
    icon.setAttribute("data-apui-slot", "icon");
  }
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
      const { TextInput, Text } = components;
      return React.createElement(TextInput, {
        label: "Website",
        addonBefore: React.createElement(Text, null, "https://"),
        addonAfter: React.createElement(Text, null, ".com"),
      });
    },
    meta: {},
  },
  {
    // An addon renders rich content, such as a component captured with `as`
    name: "addon_before_icon",
    template:
      '{% ui "icon" name="CheckOutlined" as icon %}{% ui "text_input" label="Email" addon_before=icon %}',
    buildElement({ React, components }) {
      const { TextInput, CheckOutlined } = components;
      return React.createElement(TextInput, {
        label: "Email",
        addonBefore: React.createElement(CheckOutlined),
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
  {
    // The error message is named after the given id, as Django names a form field's
    name: "caller_id_with_error_message",
    template:
      '{% ui "text_input" label="Email" id="id_email" validation_state="invalid" error_message="Enter a valid email" description="Your work email" %}',
    buildElement({ React, components }) {
      const { TextInput } = components;
      return React.createElement(TextInput, {
        label: "Email",
        id: "id_email",
        validationState: "invalid",
        errorMessage: "Enter a valid email",
        description: "Your work email",
      });
    },
    meta: {},
  },
];
