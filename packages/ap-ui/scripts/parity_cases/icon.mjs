import path from "node:path";

export const component = "icon";
export const class_prefixes = ["Icon"];

export const stylesheets = ["@alliancesoftware/icons/Icon.css.ts"];

// Icons the static renderer reads from tests/fixtures/icons/static-svg in the Python tests.
const ICON_NAMES = ["Pencil01Outlined", "CheckCircleOutlined"];

export async function loadComponents({ uiPackageDir, importDefault }) {
  const components = {};
  for (const name of ICON_NAMES) {
    components[name] = await importDefault(
      path.join(uiPackageDir, `../icons/outlined/${name}.tsx`)
    );
  }
  return components;
}

export function normalize(root, testCase, helpers) {
  // React's Icon only gets data-apui-slot from a parent's slot context (Button provides it); the
  // static icon always marks its root.
  for (const icon of root.querySelectorAll('[role="img"]')) {
    icon.setAttribute("data-apui-slot", "icon");
  }
}

function iconCase({
  name,
  templateProps = "",
  props = {},
  icon = "Pencil01Outlined",
}) {
  return {
    name,
    template: `{% ui "icon" name="${icon}"${templateProps} %}`,
    buildElement({ React, components }) {
      return React.createElement(components[icon], props);
    },
    meta: {},
  };
}

export const cases = [
  iconCase({ name: "default" }),
  ...["xxs", "xs", "sm", "md", "lg", "xl"].map((size) =>
    iconCase({
      name: `size_${size}`,
      templateProps: ` size="${size}"`,
      props: { size },
    })
  ),
  iconCase({
    name: "variant_circle",
    templateProps: ' variant="circle"',
    props: { variant: "circle" },
  }),
  iconCase({
    name: "variant_circle_outlined",
    templateProps: ' variant="circle-outlined" color="primary"',
    props: { variant: "circle-outlined", color: "primary" },
  }),
  iconCase({
    name: "color",
    icon: "CheckCircleOutlined",
    templateProps: ' color="success"',
    props: { color: "success" },
  }),
  iconCase({
    name: "aria_label",
    templateProps: ' aria_label="Edit"',
    props: { "aria-label": "Edit" },
  }),
  iconCase({
    name: "class_name",
    templateProps: ' class="custom-icon" size="sm"',
    props: { className: "custom-icon", size: "sm" },
  }),
];
