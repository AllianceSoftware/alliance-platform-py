import path from "node:path";

export const component = "checkbox";
export const class_prefixes = ["Checkbox", "FormSection", "focusRing"];

export const stylesheets = [
  "@alliancesoftware/ui/components/checkbox/Checkbox.css.ts",
  "@alliancesoftware/ui/components/form/FormSection.css.ts",
];

export async function loadComponents({ uiPackageDir, importDefault }) {
  return {
    Checkbox: await importDefault(
      path.join(uiPackageDir, "components/checkbox/Checkbox.tsx")
    ),
  };
}

export function normalize(root, testCase, helpers) {
  helpers.normalizeChoiceControls(root);
  helpers.normalizeInlineStyles(root);
}

function checkboxCase({ name, templateProps = "", props = {}, children }) {
  return {
    name,
    template: `{% ui "checkbox"${templateProps} %}${children ?? ""}{% endui %}`,
    buildElement({ React, components }) {
      return React.createElement(components.Checkbox, props, children);
    },
    meta: {},
  };
}

export const cases = [
  checkboxCase({ name: "default", children: "Accept the terms" }),
  checkboxCase({
    name: "name_and_value",
    templateProps: ' name="terms" value="yes"',
    props: { name: "terms", value: "yes" },
    children: "Accept the terms",
  }),
  checkboxCase({
    name: "default_selected",
    templateProps: " default_selected=True",
    props: { defaultSelected: true },
    children: "Accept the terms",
  }),
  checkboxCase({
    name: "selected",
    templateProps: " is_selected=True",
    props: { isSelected: true },
    children: "Accept the terms",
  }),
  checkboxCase({
    name: "indeterminate",
    templateProps: " is_indeterminate=True",
    props: { isIndeterminate: true },
    children: "Select all",
  }),
  checkboxCase({
    name: "disabled_and_read_only",
    templateProps: " is_disabled=True is_read_only=True default_selected=True",
    props: { isDisabled: true, isReadOnly: true, defaultSelected: true },
    children: "Accept the terms",
  }),
  checkboxCase({
    name: "invalid_and_required",
    templateProps: " is_invalid=True is_required=True",
    props: { isInvalid: true, isRequired: true },
    children: "Accept the terms",
  }),
  checkboxCase({
    // {% form_input %} passes validationState; react-aria reads it as React's Checkbox passes it on
    name: "validation_state_invalid",
    templateProps: ' validation_state="invalid"',
    props: { validationState: "invalid" },
    children: "Accept the terms",
  }),
  checkboxCase({
    name: "size_md",
    templateProps: ' size="md"',
    props: { size: "md" },
    children: "Accept the terms",
  }),
  checkboxCase({
    name: "id_and_aria_describedby",
    templateProps: ' id="id_terms" aria_describedby="id_terms_helptext"',
    props: { id: "id_terms", "aria-describedby": "id_terms_helptext" },
    children: "Accept the terms",
  }),
  checkboxCase({
    name: "aria_label_without_children",
    templateProps: ' aria_label="Accept the terms"',
    props: { "aria-label": "Accept the terms" },
  }),
  checkboxCase({
    name: "class_name",
    templateProps: ' class="consent"',
    props: { className: "consent" },
    children: "Accept the terms",
  }),
  checkboxCase({
    // Outside a FormSection the prop lays out the row
    name: "label_position_side",
    templateProps: ' label_position="side"',
    props: { labelPosition: "side" },
    children: "Accept the terms",
  }),
];
