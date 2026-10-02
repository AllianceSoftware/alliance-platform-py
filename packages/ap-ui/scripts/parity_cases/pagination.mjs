import path from "node:path";

export const component = "pagination";
export const class_prefixes = ["Pagination", "Button", "focusRing", "Icon"];

export const stylesheets = [
  "@alliancesoftware/ui/components/pagination/Pagination.css.ts",
  "@alliancesoftware/ui/components/button/Button.css.ts",
  "@alliancesoftware/ui/styles/base/focusRing.css.ts",
  "@alliancesoftware/icons/Icon.css.ts",
];

export async function loadComponents({ uiPackageDir, importDefault }) {
  return {};
}

export function normalize(root, testCase, helpers) {}

// Pagination has unit tests but no parity cases yet; the module lists the stylesheets its
// renderer resolves so css-mappings.json covers them.
export const cases = [];
