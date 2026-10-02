import path from "node:path";

export const component = "button_group";
export const class_prefixes = [
  "SmartOrientation",
  "ButtonGroup",
  "focusRing",
  "Button",
];

export const stylesheets = [
  "@alliancesoftware/ui/components/button/ButtonGroup.css.ts",
  "@alliancesoftware/ui/components/layout/SmartOrientation.css.ts",
  "@alliancesoftware/ui/components/button/Button.css.ts",
  "@alliancesoftware/ui/styles/base/focusRing.css.ts",
];

export async function loadComponents({ uiPackageDir, importDefault }) {
  return {
    Button: await importDefault(
      path.join(uiPackageDir, "components/button/Button.tsx")
    ),
    ButtonGroup: await importDefault(
      path.join(uiPackageDir, "components/button/ButtonGroup.tsx")
    ),
  };
}

export function normalize(root, testCase, helpers) {
  helpers.normalizeButtons(root, testCase);
  // React attaches SmartOrientation from an effect; the static renderer marks the root for the
  // collected auto-attach runtime instead.
  const componentRoot = root.firstElementChild;
  if (componentRoot?.tagName === "DIV") {
    componentRoot.setAttribute("data-apui-attach", "smart-orientation");
  }
}

export const cases = [
  {
    name: "default",
    template:
      '{% ui "button_group" %}{% ui "button" %}One{% endui %}{% endui %}',
    buildElement({ React, components }) {
      const { Button, ButtonGroup } = components;
      return React.createElement(
        ButtonGroup,
        null,
        React.createElement(Button, null, "One")
      );
    },
    meta: {},
  },
  {
    name: "slot_defaults_and_child_class_merge",
    template:
      '{% ui "button_group" variant="outlined" color="gray" size="lg" density="compact" align="end" %}{% ui "button" className="custom" %}Two{% endui %}{% endui %}',
    buildElement({ React, components }) {
      const { Button, ButtonGroup } = components;
      return React.createElement(
        ButtonGroup,
        {
          variant: "outlined",
          color: "gray",
          size: "lg",
          density: "compact",
          align: "end",
        },
        React.createElement(Button, { className: "custom" }, "Two")
      );
    },
    meta: {},
  },
  {
    name: "empty_children",
    template: '{% ui "button_group" %}{% endui %}',
    buildElement({ React, components }) {
      const { ButtonGroup } = components;
      return React.createElement(ButtonGroup, null);
    },
    meta: {},
  },
];
