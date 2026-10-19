import path from "node:path";

export const component = "select";
export const class_prefixes = [
  "LabeledInput",
  "TextInputBase",
  "focusRing",
  "Label",
  "FormSection",
  "Icon",
  "NativeSelect",
];

export const stylesheets = [
  "@alliancesoftware/ui/components/text-input/TextInputBase.css.ts",
  "@alliancesoftware/ui/components/form/LabeledInput.css.ts",
  "@alliancesoftware/ui/components/form/Label.css.ts",
  "@alliancesoftware/ui/components/form/FormSection.css.ts",
  "@alliancesoftware/ui/styles/base/focusRing.css.ts",
  "@alliancesoftware/icons/Icon.css.ts",
  "@alliancesoftware/ui/components/select/NativeSelect.css.ts",
];

export async function loadComponents({ uiPackageDir, importDefault }) {
  return {
    NativeSelect: await importDefault(
      path.join(uiPackageDir, "components/select/NativeSelect.tsx")
    ),
  };
}

export function normalize(root, testCase, helpers) {
  helpers.normalizeInputComponent(root, component);
}

// The options as a template writes them and as React elements
const COLOURS = [
  ["red", "Red"],
  ["green", "Green"],
  ["blue", "Blue"],
];
const COLOUR_OPTIONS = COLOURS.map(
  ([value, label]) => `<option value="${value}">${label}</option>`
).join("");

function colourOptions(React) {
  return COLOURS.map(([value, label]) =>
    React.createElement("option", { key: value, value }, label)
  );
}

function nativeSelect(React, components, props, children) {
  return React.createElement(components.NativeSelect, props, ...children);
}

export const cases = [
  {
    name: "default",
    template: `{% ui "select" label="Colour" %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        { label: "Colour" },
        colourOptions(React)
      );
    },
    meta: {},
  },
  {
    name: "name_and_value",
    template: `{% ui "select" label="Colour" name="colour" value="green" %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        { label: "Colour", name: "colour", value: "green" },
        colourOptions(React)
      );
    },
    meta: {},
  },
  {
    name: "default_value",
    template: `{% ui "select" label="Colour" default_value="blue" %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        { label: "Colour", defaultValue: "blue" },
        colourOptions(React)
      );
    },
    meta: {},
  },
  {
    // An option without a value attribute has its text as its value
    name: "value_of_options_without_value_attributes",
    template:
      '{% ui "select" label="Size" value="Medium" %}<option>Small</option><option>Medium</option>{% endui %}',
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        { label: "Size", value: "Medium" },
        [
          React.createElement("option", { key: "small" }, "Small"),
          React.createElement("option", { key: "medium" }, "Medium"),
        ]
      );
    },
    meta: {},
  },
  {
    // An empty value selects the option with an empty value, as a placeholder option
    name: "empty_value_selects_the_placeholder_option",
    template:
      '{% ui "select" label="Colour" value="" is_required=True %}<option value="">Choose a colour</option>' +
      `${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        { label: "Colour", value: "", isRequired: true },
        [
          React.createElement(
            "option",
            { key: "", value: "" },
            "Choose a colour"
          ),
          ...colourOptions(React),
        ]
      );
    },
    meta: {},
  },
  {
    name: "multiple_with_values",
    template: `{% ui "select" label="Colours" name="colours" is_multiple=True value=colours %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        {
          label: "Colours",
          name: "colours",
          isMultiple: true,
          value: ["red", "blue"],
        },
        colourOptions(React)
      );
    },
    meta: { context: { colours: ["red", "blue"] } },
  },
  {
    // As Django's select widget writes the options of a SelectMultiple: the native attribute and
    // selected options
    name: "multiple_attribute_and_selected_options",
    template:
      '{% ui "select" label="Colours" multiple=True %}<option value="red" selected>Red</option>' +
      '<option value="green">Green</option><option value="blue" selected>Blue</option>{% endui %}',
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        { label: "Colours", isMultiple: true, defaultValue: ["red", "blue"] },
        colourOptions(React)
      );
    },
    meta: {},
  },
  {
    name: "option_groups",
    template:
      '{% ui "select" label="Animal" value="emu" %}' +
      '<optgroup label="Mammals"><option value="kangaroo">Kangaroo</option><option value="wombat">Wombat</option></optgroup>' +
      '<optgroup label="Birds"><option value="emu">Emu</option><option value="cassowary" disabled>Cassowary</option></optgroup>' +
      '<optgroup label="Reptiles" disabled><option value="goanna">Goanna</option></optgroup>' +
      "{% endui %}",
    buildElement({ React, components }) {
      const option = (value, label, props = {}) =>
        React.createElement("option", { key: value, value, ...props }, label);
      return nativeSelect(
        React,
        components,
        { label: "Animal", value: "emu" },
        [
          React.createElement(
            "optgroup",
            { key: "mammals", label: "Mammals" },
            [option("kangaroo", "Kangaroo"), option("wombat", "Wombat")]
          ),
          React.createElement("optgroup", { key: "birds", label: "Birds" }, [
            option("emu", "Emu"),
            option("cassowary", "Cassowary", { disabled: true }),
          ]),
          React.createElement(
            "optgroup",
            { key: "reptiles", label: "Reptiles", disabled: true },
            [option("goanna", "Goanna")]
          ),
        ]
      );
    },
    meta: {},
  },
  {
    name: "input_size_md",
    template: `{% ui "select" label="Colour" input_size="md" %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        { label: "Colour", inputSize: "md" },
        colourOptions(React)
      );
    },
    meta: {},
  },
  {
    name: "disabled",
    template: `{% ui "select" label="Colour" is_disabled=True %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        { label: "Colour", isDisabled: true },
        colourOptions(React)
      );
    },
    meta: {},
  },
  {
    name: "required",
    template: `{% ui "select" label="Colour" is_required=True %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        { label: "Colour", isRequired: true },
        colourOptions(React)
      );
    },
    meta: {},
  },
  {
    name: "description",
    template: `{% ui "select" label="Colour" description="Shown on your profile" %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        { label: "Colour", description: "Shown on your profile" },
        colourOptions(React)
      );
    },
    meta: {},
  },
  {
    name: "invalid_with_error_message",
    template: `{% ui "select" label="Colour" validation_state="invalid" error_message="Choose a colour" description="Your favourite" %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        {
          label: "Colour",
          validationState: "invalid",
          errorMessage: "Choose a colour",
          description: "Your favourite",
        },
        colourOptions(React)
      );
    },
    meta: {},
  },
  {
    name: "is_invalid",
    template: `{% ui "select" label="Colour" is_invalid=True error_message="Choose a colour" %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        { label: "Colour", isInvalid: true, errorMessage: "Choose a colour" },
        colourOptions(React)
      );
    },
    meta: {},
  },
  {
    name: "valid",
    template: `{% ui "select" label="Colour" validation_state="valid" %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        { label: "Colour", validationState: "valid" },
        colourOptions(React)
      );
    },
    meta: {},
  },
  {
    // A list box has no chevron; its validation icon stays
    name: "multiple_invalid",
    template: `{% ui "select" label="Colours" is_multiple=True validation_state="invalid" error_message="Choose a colour" %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        {
          label: "Colours",
          isMultiple: true,
          validationState: "invalid",
          errorMessage: "Choose a colour",
        },
        colourOptions(React)
      );
    },
    meta: {},
  },
  {
    // A select showing more than one row is a list box too
    name: "size_list_box",
    template: `{% ui "select" label="Colour" size=3 %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        { label: "Colour", size: 3 },
        colourOptions(React)
      );
    },
    meta: {},
  },
  {
    name: "label_position_side_align_end",
    template: `{% ui "select" label="Colour" label_position="side" label_align="end" %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        { label: "Colour", labelPosition: "side", labelAlign: "end" },
        colourOptions(React)
      );
    },
    meta: {},
  },
  {
    name: "select_attributes",
    template: `{% ui "select" label="Country" name="country" auto_complete="country" form="profile" title="Where you live" %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        {
          label: "Country",
          name: "country",
          autoComplete: "country",
          form: "profile",
          title: "Where you live",
        },
        colourOptions(React)
      );
    },
    meta: {},
  },
  {
    name: "custom_class_names",
    template: `{% ui "select" label="Colour" class="custom-root" input_class_name="custom-select" %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        {
          label: "Colour",
          className: "custom-root",
          inputClassName: "custom-select",
        },
        colourOptions(React)
      );
    },
    meta: {},
  },
  {
    name: "caller_id_and_aria_describedby",
    template: `{% ui "select" label="Colour" id="colour" aria_describedby="external-desc" description="Some description" %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        {
          label: "Colour",
          id: "colour",
          "aria-describedby": "external-desc",
          description: "Some description",
        },
        colourOptions(React)
      );
    },
    meta: {},
  },
  {
    // The error message is named after the given id, as Django names a form field's
    name: "caller_id_with_error_message",
    template: `{% ui "select" label="Colour" id="id_colour" validation_state="invalid" error_message="Choose a colour" description="Your favourite" %}${COLOUR_OPTIONS}{% endui %}`,
    buildElement({ React, components }) {
      return nativeSelect(
        React,
        components,
        {
          label: "Colour",
          id: "id_colour",
          validationState: "invalid",
          errorMessage: "Choose a colour",
          description: "Your favourite",
        },
        colourOptions(React)
      );
    },
    meta: {},
  },
];
