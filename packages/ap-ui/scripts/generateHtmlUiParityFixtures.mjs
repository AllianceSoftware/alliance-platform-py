#!/usr/bin/env node

// Renders every parity case with the React components from @alliancesoftware/ui and writes
// `tests/fixtures/ui_html_<component>_parity.json` per case module, plus
// `tests/fixtures/css-mappings.json` with the class mappings of every stylesheet the modules list.
// Run it through `syncHtmlUiParityFixtures.sh`, which runs this file under vite-node inside the ui
// package with vanilla-extract's debug identifiers (`Button_baseButton__1a2b3c`).
//
// Each module in `parity_cases/` (names starting with `_` are skipped) describes one component:
//
// - `component`: the static component name, also used in the fixture file name.
// - `cases`: `{ name, template, buildElement({ React, components }), meta, ...flags }` objects.
// - `class_prefixes` / `keep_class_tokens`: the vanilla-extract scopes a fixture compares, see
//   `normalizeClassTokens` in `parity_cases/_helpers.mjs`. Both are written into the fixture so the
//   Python side reduces the static output the same way.
// - `stylesheets`: the `.css.ts` paths the component's static renderers resolve, written as they
//   request them (`@alliancesoftware/ui/components/button/Button.css.ts`). The Python parity tests
//   read class names from `css-mappings.json`, which is keyed by these paths.
// - `loadComponents({ uiPackageDir, importDefault, importBareModule })`: the components the cases
//   build with, passed to `buildElement` as `components`.
// - `normalize(root, testCase, helpers)`: React-side normalisation for the component family,
//   applied to the parsed markup; `helpers` is `parity_cases/_helpers.mjs`.
//
// Every case's markup is parsed, stripped of the React-only attributes all components share,
// passed to the module's `normalize`, reduced to the compared class tokens and serialised.
//
// Usage: generateHtmlUiParityFixtures.mjs [component]
//
// With a component only that fixture is written; `css-mappings.json` always covers every module.

import fs from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { pathToFileURL } from "node:url";

import * as helpers from "./parity_cases/_helpers.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CASE_MODULE_DIR = path.join(__dirname, "parity_cases");
const FIXTURE_DIR = path.resolve(__dirname, "../tests/fixtures");
const CSS_MAPPINGS_PATH = path.join(FIXTURE_DIR, "css-mappings.json");

const uiPackageDirValue = process.env.AP_UI_UI_PACKAGE_DIR;
if (!uiPackageDirValue) {
  throw new Error(
    "AP_UI_UI_PACKAGE_DIR must point to the @alliancesoftware/ui package"
  );
}
const uiPackageDir = path.resolve(uiPackageDirValue);
// The Vite plugin's own extractor, so the mappings have exactly the shape Django reads at runtime.
const VANILLA_EXTRACT_PLUGIN_SOURCE = path.join(
  uiPackageDir,
  "../vite-plugin-django-vanilla-extract/src/djangoVanillaExtractPlugin.ts"
);
const uiRequire = createRequire(path.join(uiPackageDir, "package.json"));
const { JSDOM } = await import(pathToFileURL(uiRequire.resolve("jsdom")).href);
let prettierFormatPromise;

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
      "Failed to load React rendering runtime. Ensure this script is run under a TS-aware runtime (for example vite-node)."
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

async function loadCaseModules() {
  const fileNames = (await fs.readdir(CASE_MODULE_DIR))
    .filter(
      (fileName) => fileName.endsWith(".mjs") && !fileName.startsWith("_")
    )
    .sort();
  const caseModules = [];
  for (const fileName of fileNames) {
    const modulePath = path.join(CASE_MODULE_DIR, fileName);
    const caseModule = await import(pathToFileURL(modulePath).href);
    const { component, cases, loadComponents, normalize, stylesheets } =
      caseModule;
    if (
      !component ||
      !Array.isArray(cases) ||
      typeof loadComponents !== "function" ||
      typeof normalize !== "function" ||
      !Array.isArray(stylesheets) ||
      !stylesheets.every((stylesheet) => stylesheet.endsWith(".css.ts"))
    ) {
      throw new Error(
        `Invalid parity case module ${modulePath}: it must export component, cases, ` +
          "loadComponents, normalize and stylesheets (a list of .css.ts paths)"
      );
    }
    caseModules.push(caseModule);
  }
  return caseModules;
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

function parseHtml(html) {
  const document = new JSDOM("<!doctype html><body></body>").window.document;
  document.body.innerHTML = html;
  return document.body;
}

function normalizeRenderedHtml(
  caseModule,
  testCase,
  html,
  allowedPrefixes,
  keepClassTokens
) {
  if (!html.trim()) {
    return "";
  }

  const root = parseHtml(html);
  removeReactOnlyAttributes(root);
  caseModule.normalize(root, testCase, helpers);
  helpers.normalizeClassAttributes(root, allowedPrefixes, keepClassTokens);
  return helpers.serializeHtml(root);
}

// React Aria markup every component shares that the static renderers never emit.
function removeReactOnlyAttributes(root) {
  helpers.removeAttributeMatching(root, "data-react-aria-pressable", "true");
  helpers.removeAttributeMatching(root, "tabindex", "0");
}

async function generateFixture(caseModule, runtime) {
  const {
    component,
    cases,
    class_prefixes: classPrefixes = [],
    keep_class_tokens: keepClassTokensList = [],
  } = caseModule;
  const allowedPrefixes = new Set(classPrefixes);
  const keepClassTokens = new Set(keepClassTokensList);
  const components = await caseModule.loadComponents({
    uiPackageDir,
    importDefault,
    importBareModule,
  });

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
        testCase.buildElement({ React: runtime.React, components })
      )
    );
    if (currentUrl) {
      delete globalThis.globalSsrContext;
    }
    const normalizedHtml = normalizeRenderedHtml(
      caseModule,
      testCase,
      html,
      allowedPrefixes,
      keepClassTokens
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
    class_prefixes: classPrefixes,
    keep_class_tokens: keepClassTokensList,
    cases: serializedCases,
  };

  const fixturePath = path.join(
    FIXTURE_DIR,
    `ui_html_${component}_parity.json`
  );
  await writeJson(fixturePath, fixture);
  return fixturePath;
}

async function writeCssMappings(caseModules) {
  const { extractMappingFromModule } = await import(
    pathToFileURL(VANILLA_EXTRACT_PLUGIN_SOURCE).href
  );
  const stylesheets = [
    ...new Set(caseModules.flatMap(({ stylesheets }) => stylesheets)),
  ].sort();
  const mappings = {};
  for (const stylesheet of stylesheets) {
    // Bare specifiers resolve through the JS workspace's node_modules, as in a project.
    mappings[stylesheet] = extractMappingFromModule(
      await importBareModule(stylesheet)
    );
  }
  await writeJson(CSS_MAPPINGS_PATH, mappings);
  return CSS_MAPPINGS_PATH;
}

async function writeJson(filePath, value) {
  const formatted = await formatFixtureJson(
    `${JSON.stringify(value, null, 2)}\n`
  );
  await fs.writeFile(filePath, formatted, "utf8");
}

async function main() {
  const onlyComponent = process.argv[2];
  const caseModules = await loadCaseModules();
  const selectedModules = onlyComponent
    ? caseModules.filter(({ component }) => component === onlyComponent)
    : caseModules;
  if (!selectedModules.length) {
    throw new Error(
      `No parity case module for component "${onlyComponent}". Known components: ` +
        caseModules.map(({ component }) => component).join(", ")
    );
  }
  const runtime = await loadRendererRuntime();
  for (const caseModule of selectedModules) {
    const fixturePath = await generateFixture(caseModule, runtime);
    process.stdout.write(`Wrote ${fixturePath}\n`);
  }
  const mappingsPath = await writeCssMappings(caseModules);
  process.stdout.write(`Wrote ${mappingsPath}\n`);
}

await main();
