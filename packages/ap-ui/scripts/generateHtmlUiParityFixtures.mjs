#!/usr/bin/env node

import fs from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { pathToFileURL } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CASE_MODULES = [
  "./parity_cases/button.mjs",
  "./parity_cases/button_group.mjs",
  "./parity_cases/text_input.mjs",
  "./parity_cases/number_input.mjs",
  "./parity_cases/text_area.mjs",
  "./parity_cases/inline_alert.mjs",
  "./parity_cases/table.mjs",
  "./parity_cases/menubar.mjs",
];

const BUTTON_COMPONENTS = new Set(["button", "button_group"]);
const INPUT_COMPONENTS = new Set(["text_input", "number_input", "text_area"]);
const INLINE_ALERT_COMPONENTS = new Set(["inline_alert"]);
const TABLE_COMPONENTS = new Set(["table"]);
const MENUBAR_COMPONENTS = new Set(["menubar"]);

const uiPackageDirValue = process.env.AP_UI_UI_PACKAGE_DIR;
if (!uiPackageDirValue) {
  throw new Error(
    "AP_UI_UI_PACKAGE_DIR must point to the @alliancesoftware/ui package",
  );
}
const uiPackageDir = path.resolve(uiPackageDirValue);
const uiRequire = createRequire(path.join(uiPackageDir, "package.json"));
const { JSDOM } = await import(pathToFileURL(uiRequire.resolve("jsdom")).href);
let prettierFormatPromise;
const parityComponentRuntimeCache = new Map();

async function loadRendererRuntime() {
  const [reactModule, reactDomServerModule] = await Promise.all([
    import("react"),
    import("react-dom/server"),
  ]);

  const React = reactModule.default ?? reactModule;
  const renderToStaticMarkup =
    reactDomServerModule.renderToStaticMarkup ??
    reactDomServerModule.default?.renderToStaticMarkup;

  if (!React?.createElement || typeof renderToStaticMarkup !== "function") {
    throw new Error(
      "Failed to load React rendering runtime. Ensure this script is run under a TS-aware runtime (for example vite-node).",
    );
  }

  return { React, renderToStaticMarkup };
}

async function importDefault(modulePath) {
  const module = await import(pathToFileURL(modulePath).href);
  return module.default ?? module;
}

async function importBareModule(specifier) {
  return import(specifier);
}

async function loadParityComponents(component) {
  if (parityComponentRuntimeCache.has(component)) {
    return parityComponentRuntimeCache.get(component);
  }

  let components;
  if (component === "button") {
    components = {
      Button: await importDefault(
        path.join(uiPackageDir, "components/button/Button.tsx"),
      ),
    };
  } else if (component === "button_group") {
    components = {
      Button: await importDefault(
        path.join(uiPackageDir, "components/button/Button.tsx"),
      ),
      ButtonGroup: await importDefault(
        path.join(uiPackageDir, "components/button/ButtonGroup.tsx"),
      ),
    };
  } else if (component === "text_input") {
    components = {
      TextInput: await importDefault(
        path.join(uiPackageDir, "components/text-input/TextInput.tsx"),
      ),
    };
  } else if (component === "text_area") {
    components = {
      TextArea: await importDefault(
        path.join(uiPackageDir, "components/text-input/TextArea.tsx"),
      ),
    };
  } else if (component === "number_input") {
    components = {
      NumberInput: await importDefault(
        path.join(uiPackageDir, "components/number-input/NumberInput.tsx"),
      ),
    };
  } else if (component === "inline_alert") {
    components = {
      InlineAlert: await importDefault(
        path.join(uiPackageDir, "components/inline-alert/InlineAlert.tsx"),
      ),
      Content: await importDefault(
        path.join(uiPackageDir, "components/layout/Content.tsx"),
      ),
      Heading: await importDefault(
        path.join(uiPackageDir, "components/layout/Heading.tsx"),
      ),
      Header: await importDefault(
        path.join(uiPackageDir, "components/layout/Header.tsx"),
      ),
      Footer: await importDefault(
        path.join(uiPackageDir, "components/layout/Footer.tsx"),
      ),
      AlertCircleOutlined: await importDefault(
        path.join(uiPackageDir, "../icons/outlined/AlertCircleOutlined.tsx"),
      ),
      AlertTriangleOutlined: await importDefault(
        path.join(uiPackageDir, "../icons/outlined/AlertTriangleOutlined.tsx"),
      ),
      CheckCircleOutlined: await importDefault(
        path.join(uiPackageDir, "../icons/outlined/CheckCircleOutlined.tsx"),
      ),
      InfoCircleOutlined: await importDefault(
        path.join(uiPackageDir, "../icons/outlined/InfoCircleOutlined.tsx"),
      ),
    };
  } else if (component === "table") {
    // Table itself comes from the ui package; the collection components (TableHeader etc.)
    // are the react-stately ones the ui package re-exports.
    const reactStately = await importBareModule("react-stately");
    components = {
      Table: await importDefault(
        path.join(uiPackageDir, "components/table/Table.tsx"),
      ),
      ColumnHeaderLink: await importDefault(
        path.join(uiPackageDir, "components/table/ColumnHeaderLink.tsx"),
      ),
      TableHeader: reactStately.TableHeader,
      TableBody: reactStately.TableBody,
      Column: reactStately.Column,
      Row: reactStately.Row,
      Cell: reactStately.Cell,
    };
  } else if (component === "menubar") {
    const Menubar = await importDefault(
      path.join(uiPackageDir, "components/menu-bar/Menubar.tsx"),
    );
    components = {
      Menubar,
      Item: Menubar.Item,
      SubMenu: Menubar.SubMenu,
      Section: Menubar.Section,
      Pencil01Outlined: await importDefault(
        path.join(uiPackageDir, "../icons/outlined/Pencil01Outlined.tsx"),
      ),
    };
  } else {
    throw new Error(`Unsupported parity component runtime: ${component}`);
  }

  parityComponentRuntimeCache.set(component, components);
  return components;
}

async function formatFixtureJson(content) {
  if (!prettierFormatPromise) {
    prettierFormatPromise = (async () => {
      try {
        const prettierPath = uiRequire.resolve("prettier");
        const prettierModule = await import(pathToFileURL(prettierPath).href);
        return prettierModule.format ?? prettierModule.default?.format ?? null;
      } catch {
        return null;
      }
    })();
  }
  const prettierFormat = await prettierFormatPromise;
  if (!prettierFormat) {
    return content;
  }
  return prettierFormat(content, { parser: "json" });
}

function captureWarnings(run) {
  const warnings = [];
  const originalWarn = console.warn;
  console.warn = (...args) => {
    warnings.push(args.map(String).join(" "));
  };
  try {
    const html = run();
    return { html, warnings };
  } finally {
    console.warn = originalWarn;
  }
}

function dedupeTokens(tokens) {
  const seen = new Set();
  return tokens.filter((token) => {
    if (!token || seen.has(token)) {
      return false;
    }
    seen.add(token);
    return true;
  });
}

function tokenizeClasses(value) {
  if (!value) {
    return [];
  }
  return String(value).trim().split(/\s+/).filter(Boolean);
}

function normalizeClassTokens(classValue, allowedPrefixes, keepClassTokens) {
  const normalized = [];
  for (const originalToken of tokenizeClasses(classValue)) {
    const hashIndex = originalToken.lastIndexOf("__");
    const hadHash = hashIndex !== -1;
    const token = hadHash ? originalToken.slice(0, hashIndex) : originalToken;
    if (!token) {
      continue;
    }

    if (token.includes("_")) {
      const prefix = token.split("_", 1)[0];
      if (hadHash && !allowedPrefixes.has(prefix)) {
        continue;
      }
    } else if (hadHash && !allowedPrefixes.has(token)) {
      continue;
    }
    normalized.push(token);
  }

  const deduped = dedupeTokens(normalized);
  return deduped.filter((token) => {
    if (keepClassTokens.has(token)) {
      return true;
    }
    const hasChildToken = deduped.some(
      (other) => other !== token && other.startsWith(`${token}_`),
    );
    if (hasChildToken) {
      return false;
    }
    if (token.endsWith("Base")) {
      const root = token.slice(0, -4);
      if (
        deduped.some((other) => other !== token && other.startsWith(`${root}_`))
      ) {
        return false;
      }
    }
    return true;
  });
}

function parseHtml(html) {
  const document = new JSDOM("<!doctype html><body></body>").window.document;
  document.body.innerHTML = html;
  return document.body;
}

function elements(root) {
  return [root, ...root.querySelectorAll("*")].filter(
    (node) => node.nodeType === 1,
  );
}

function removeAttributeMatching(root, name, value = null) {
  for (const element of elements(root)) {
    if (
      element.hasAttribute(name) &&
      (value === null || element.getAttribute(name) === value)
    ) {
      element.removeAttribute(name);
    }
  }
}

function normalizeInlineStyles(root) {
  for (const element of elements(root)) {
    const value = element.getAttribute("style");
    if (value !== null) {
      element.setAttribute(
        "style",
        value.replace(/:\s*/g, ": ").replace(/;\s*/g, "; ").trim(),
      );
    }
  }
}

function collectReferencedReactAriaIds(root, attributeNames) {
  const referenced = new Set();
  for (const element of elements(root)) {
    for (const name of attributeNames) {
      for (const token of (element.getAttribute(name) ?? "").split(/\s+/)) {
        if (token.startsWith("react-aria-")) {
          referenced.add(token);
        }
      }
    }
  }
  return referenced;
}

function removeUnreferencedReactAriaIds(root, referenced) {
  for (const element of elements(root)) {
    const id = element.getAttribute("id");
    if (id?.startsWith("react-aria-") && !referenced.has(id)) {
      element.removeAttribute("id");
    }
  }
}

function remapReactAriaIds(root, component) {
  const idMap = new Map();
  const idPrefix = `apui-${component.replaceAll("_", "-")}-`;
  for (const element of elements(root)) {
    for (const attribute of Array.from(element.attributes)) {
      const value = attribute.value.replace(/react-aria-[^"'\s]+/g, (token) => {
        if (!idMap.has(token)) {
          idMap.set(token, `${idPrefix}${idMap.size + 1}`);
        }
        return idMap.get(token);
      });
      if (value !== attribute.value) {
        element.setAttribute(attribute.name, value);
      }
    }
  }
}

function normalizeInputComponent(root, component) {
  for (const element of elements(root)) {
    const labelledBy = element.getAttribute("aria-labelledby");
    if (labelledBy !== null) {
      const tokens = labelledBy
        .split(/\s+/)
        .filter((token) => token && !token.startsWith("react-aria-"));
      if (tokens.length) {
        element.setAttribute("aria-labelledby", tokens.join(" "));
      } else {
        element.removeAttribute("aria-labelledby");
      }
    }
  }

  const presentIds = new Set(
    elements(root)
      .map((element) => element.getAttribute("id"))
      .filter((id) => id?.startsWith("react-aria-")),
  );
  for (const element of elements(root)) {
    const describedBy = element.getAttribute("aria-describedby");
    if (describedBy !== null) {
      const tokens = describedBy
        .split(/\s+/)
        .filter(
          (token) =>
            token &&
            (!token.startsWith("react-aria-") || presentIds.has(token)),
        );
      if (tokens.length) {
        element.setAttribute("aria-describedby", tokens.join(" "));
      } else {
        element.removeAttribute("aria-describedby");
      }
    }
  }

  const referenced = collectReferencedReactAriaIds(root, [
    "for",
    "aria-controls",
    "aria-errormessage",
    "aria-describedby",
  ]);
  removeUnreferencedReactAriaIds(root, referenced);
  remapReactAriaIds(root, component);
  normalizeInlineStyles(root);
}

function prependAttribute(element, name, value) {
  const attributes = Array.from(element.attributes).map((attribute) => [
    attribute.name,
    attribute.value,
  ]);
  for (const attribute of Array.from(element.attributes)) {
    element.removeAttribute(attribute.name);
  }
  element.setAttribute(name, value);
  for (const [attributeName, attributeValue] of attributes) {
    if (attributeName !== name) {
      element.setAttribute(attributeName, attributeValue);
    }
  }
}

function normalizeTableComponent(root, component) {
  const interactiveRoles = new Set([
    "grid",
    "rowgroup",
    "row",
    "columnheader",
    "gridcell",
  ]);
  for (const element of elements(root)) {
    if (interactiveRoles.has(element.getAttribute("role"))) {
      element.removeAttribute("role");
    }
    for (const attribute of [
      "tabindex",
      "aria-colindex",
      "aria-rowindex",
      "aria-colcount",
      "aria-rowcount",
      "aria-colspan",
      "aria-rowspan",
      "aria-multiselectable",
      "aria-selected",
      "data-collection",
      "data-key",
    ]) {
      element.removeAttribute(attribute);
    }
    const href = element.getAttribute("href");
    if (href?.startsWith("http://testserver")) {
      element.setAttribute("href", href.slice("http://testserver".length));
    }
    const style = element.getAttribute("style");
    if (style !== null) {
      const normalizedStyle = style.replace(
        /(--[\w-]+)__[a-z0-9]+\s*:/g,
        "$1: ",
      );
      element.setAttribute("style", normalizedStyle);
    }
  }
  for (const heading of root.querySelectorAll("th")) {
    prependAttribute(heading, "scope", "col");
  }
  for (const row of root.querySelectorAll("tbody > tr")) {
    const classNames = tokenizeClasses(row.getAttribute("class")).filter(
      (className) =>
        className !== "Table_row" && !className.startsWith("Table_row__"),
    );
    if (classNames.length) {
      row.setAttribute("class", classNames.join(" "));
    } else {
      row.removeAttribute("class");
    }
  }
  for (const icon of root.querySelectorAll('[role="img"]')) {
    icon.setAttribute("data-apui-slot", "icon");
  }
  normalizeInputComponent(root, component);
}

function normalizeMenubarComponent(root, component) {
  root.querySelector('li[data-key="____more_items_from_overflow"]')?.remove();
  for (const element of elements(root)) {
    for (const attribute of [
      "tabindex",
      "data-key",
      "data-collection",
      "data-has-leading-icon",
    ]) {
      element.removeAttribute(attribute);
    }
    if (element.getAttribute("aria-disabled") === "false") {
      element.removeAttribute("aria-disabled");
    }
    if (element.getAttribute("aria-hidden") === "false") {
      element.removeAttribute("aria-hidden");
    }
    if (element.hasAttribute("class")) {
      element.classList.forEach((token) => {
        if (/^Menubar_hasLeadingIcon__/.test(token)) {
          element.classList.remove(token);
        }
      });
      if (!element.className) {
        element.removeAttribute("class");
      }
    }
    const style = element.getAttribute("style");
    if (style !== null) {
      const normalizedStyle = style.replace(
        /(--[\w-]+)__[a-z0-9]+\s*:/g,
        "$1: ",
      );
      element.setAttribute("style", normalizedStyle);
    }
  }

  const referenced = collectReferencedReactAriaIds(root, [
    "for",
    "aria-controls",
    "aria-labelledby",
    "aria-describedby",
    "aria-errormessage",
  ]);
  removeUnreferencedReactAriaIds(root, referenced);
  remapReactAriaIds(root, component);
  for (const icon of root.querySelectorAll('[role="img"]')) {
    icon.setAttribute("data-apui-slot", "icon");
  }
}

function normalizeInlineAlertComponent(root) {
  const alertRoot = root.querySelector('[data-apui="inline-alert"]');
  const alertInner = alertRoot?.firstElementChild;
  if (!alertRoot || !alertInner) {
    return;
  }
  const contentChildren = Array.from(alertInner.children).filter(
    (child) => !child.hasAttribute("data-alerticon"),
  );
  if (
    contentChildren.length === 1 &&
    contentChildren[0].tagName === "SECTION" &&
    tokenizeClasses(contentChildren[0].getAttribute("class")).some((token) =>
      token.startsWith("InlineAlert_content")
    )
  ) {
    alertRoot.setAttribute("data-only-content", "true");
    alertInner.classList.add("InlineAlert_onlyContent");
  }
  normalizeInlineStyles(root);
}

function injectButtonGroupRuntime(root) {
  const componentRoot = root.firstElementChild;
  if (!componentRoot || componentRoot.tagName !== "DIV") {
    return;
  }
  componentRoot.setAttribute("data-apui-attach", "smart-orientation");
}

function serializeHtml(root) {
  return root.innerHTML.replace(
    /<(area|base|br|col|embed|hr|img|input|link|meta|param|source|track|wbr)([^>]*)>/gi,
    "<$1$2/>",
  );
}

function normalizeRenderedHtml(
  component,
  testCase,
  html,
  allowedPrefixes,
  keepClassTokens,
) {
  if (!html.trim()) {
    return "";
  }

  const root = parseHtml(html);
  removeAttributeMatching(root, "data-react-aria-pressable", "true");
  removeAttributeMatching(root, "tabindex", "0");

  if (BUTTON_COMPONENTS.has(component)) {
    removeAttributeMatching(root, "type", "button");
    if (!testCase.template.includes('data-apui-slot="icon"')) {
      removeAttributeMatching(root, "data-icon-only", "true");
    }
  }
  if (INPUT_COMPONENTS.has(component)) {
    normalizeInputComponent(root, component);
  }
  if (INLINE_ALERT_COMPONENTS.has(component)) {
    normalizeInlineAlertComponent(root);
  }
  if (TABLE_COMPONENTS.has(component)) {
    normalizeTableComponent(root, component);
  }
  if (MENUBAR_COMPONENTS.has(component)) {
    normalizeMenubarComponent(root, component);
  }

  for (const element of elements(root)) {
    if (!element.hasAttribute("class")) {
      continue;
    }
    const classTokens = normalizeClassTokens(
      element.getAttribute("class"),
      allowedPrefixes,
      keepClassTokens,
    );
    if (classTokens.length) {
      element.setAttribute("class", classTokens.join(" "));
    } else {
      element.removeAttribute("class");
    }
  }
  if (component === "button_group") {
    injectButtonGroupRuntime(root);
  }
  return serializeHtml(root);
}
async function generateFixtureFromModule(modulePath, runtime) {
  const caseModule = await import(new URL(modulePath, import.meta.url));
  const {
    component,
    cases,
    class_prefixes: classPrefixes = [],
    keep_class_tokens: keepClassTokensList = [],
  } = caseModule;
  const allowedPrefixes = new Set(classPrefixes);
  const keepClassTokens = new Set(keepClassTokensList);
  const parityComponents = await loadParityComponents(component);

  if (!component || !Array.isArray(cases)) {
    throw new Error(`Invalid parity case module at ${modulePath}`);
  }

  const serializedCases = [];
  for (const testCase of cases) {
    // Cases may specify the current URL (path + query) the render happens at; ColumnHeaderLink
    // reads it from globalSsrContext during SSR. The matching Python parity test builds a
    // request for the same URL. The origin is stripped again during normalization.
    const currentUrl = testCase.meta?.current_url;
    if (currentUrl) {
      globalThis.globalSsrContext = {
        currentUrl: new URL(currentUrl, "http://testserver").toString(),
      };
    }
    const { html, warnings } = captureWarnings(() =>
      runtime.renderToStaticMarkup(
        testCase.buildElement({
          React: runtime.React,
          components: parityComponents,
        }),
      ),
    );
    if (currentUrl) {
      delete globalThis.globalSsrContext;
    }
    const normalizedHtml = normalizeRenderedHtml(
      component,
      testCase,
      html,
      allowedPrefixes,
      keepClassTokens,
    );
    serializedCases.push({
      name: testCase.name,
      template: testCase.template,
      expected_html: normalizedHtml,
      expected_warnings: warnings,
      meta: testCase.meta ?? {},
    });
  }

  const fixture = {
    component,
    cases: serializedCases,
  };

  const fixturePath = path.resolve(
    __dirname,
    "../tests/fixtures",
    `ui_html_${component}_parity.json`,
  );
  const serializedFixture = `${JSON.stringify(fixture, null, 2)}\n`;
  const formattedFixture = await formatFixtureJson(serializedFixture);
  await fs.writeFile(fixturePath, formattedFixture, "utf8");
  return fixturePath;
}

async function main() {
  const runtime = await loadRendererRuntime();
  const onlyComponent = process.argv[2];
  const modulePaths = CASE_MODULES;
  for (const modulePath of modulePaths) {
    const caseModule = await import(new URL(modulePath, import.meta.url));
    if (onlyComponent && caseModule.component !== onlyComponent) {
      continue;
    }
    const fixturePath = await generateFixtureFromModule(modulePath, runtime);
    process.stdout.write(`Wrote ${fixturePath}\n`);
  }
}

await main();
