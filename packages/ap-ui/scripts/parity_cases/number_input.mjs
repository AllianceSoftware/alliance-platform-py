import path from "node:path";

export const component = "number_input";
export const class_prefixes = [
  "LabeledInput",
  "TextInputBase",
  "focusRing",
  "Label",
  "FormSection",
  "Icon",
  "NumberInput",
];

export const stylesheets = [
  "@alliancesoftware/ui/components/text-input/TextInputBase.css.ts",
  "@alliancesoftware/ui/components/form/LabeledInput.css.ts",
  "@alliancesoftware/ui/components/form/Label.css.ts",
  "@alliancesoftware/ui/components/form/FormSection.css.ts",
  "@alliancesoftware/ui/styles/base/focusRing.css.ts",
  "@alliancesoftware/icons/Icon.css.ts",
  "@alliancesoftware/ui/components/number-input/NumberInput.css.ts",
];

export async function loadComponents({ uiPackageDir, importDefault }) {
  return {
    NumberInput: await importDefault(
      path.join(uiPackageDir, "components/number-input/NumberInput.tsx")
    ),
  };
}

export function normalize(root, testCase, helpers) {
  // React submits the field through a hidden input rendered after the root. The static renderer
  // keeps the name on the visible input so the field submits without JavaScript, and the attach
  // runtime creates its own hidden input on the client, so the SSR hidden input is not compared.
  for (const input of root.querySelectorAll('input[type="hidden"]')) {
    input.remove();
  }
  helpers.normalizeInputComponent(root, component);
}

export const cases = [
  {
    name: "default",
    template: '{% ui "number_input" label="Quantity" %}',
    buildElement({ React, components }) {
      const { NumberInput } = components;
      return React.createElement(NumberInput, { label: "Quantity" });
    },
    meta: {},
  },
  {
    name: "name_and_default_value",
    template:
      '{% ui "number_input" label="Quantity" name="qty" defaultValue=5 %}',
    buildElement({ React, components }) {
      const { NumberInput } = components;
      return React.createElement(NumberInput, {
        label: "Quantity",
        name: "qty",
        defaultValue: 5,
      });
    },
    meta: {},
  },
  {
    // minValue/maxValue/step have no static DOM representation in the React output (the input is
    // rendered as type="text" with inputmode="numeric" and clamping happens client side), so this
    // case documents that they are accepted without changing the rendered HTML.
    name: "min_max_step",
    template:
      '{% ui "number_input" label="Quantity" minValue=1 maxValue=20 step=1 %}',
    buildElement({ React, components }) {
      const { NumberInput } = components;
      return React.createElement(NumberInput, {
        label: "Quantity",
        minValue: 1,
        maxValue: 20,
        step: 1,
      });
    },
    meta: {},
  },
  {
    name: "hide_step_buttons",
    template:
      '{% ui "number_input" label="Price" defaultValue=12.5 hideStepButtons=True %}',
    buildElement({ React, components }) {
      const { NumberInput } = components;
      return React.createElement(NumberInput, {
        label: "Price",
        defaultValue: 12.5,
        hideStepButtons: true,
      });
    },
    meta: {},
  },
  {
    name: "invalid_with_error_message",
    template:
      '{% ui "number_input" label="Age" name="age" isInvalid=True errorMessage="Age is required" %}',
    buildElement({ React, components }) {
      const { NumberInput } = components;
      return React.createElement(NumberInput, {
        label: "Age",
        name: "age",
        isInvalid: true,
        errorMessage: "Age is required",
      });
    },
    meta: {},
  },
  {
    name: "disabled",
    template: '{% ui "number_input" label="Quantity" isDisabled=True %}',
    buildElement({ React, components }) {
      const { NumberInput } = components;
      return React.createElement(NumberInput, {
        label: "Quantity",
        isDisabled: true,
      });
    },
    meta: {},
  },
  {
    name: "addon_after_with_step_buttons",
    template:
      '{% ui "number_input" label="Price" addonAfter="AUD" defaultValue=12.5 %}',
    buildElement({ React, components }) {
      const { NumberInput } = components;
      return React.createElement(NumberInput, {
        label: "Price",
        addonAfter: "AUD",
        defaultValue: 12.5,
      });
    },
    meta: {},
  },
  {
    name: "custom_class_names",
    template:
      '{% ui "number_input" label="Quantity" className="custom-root" inputClassName="custom-input" %}',
    buildElement({ React, components }) {
      const { NumberInput } = components;
      return React.createElement(NumberInput, {
        label: "Quantity",
        className: "custom-root",
        inputClassName: "custom-input",
      });
    },
    meta: {},
  },
];
