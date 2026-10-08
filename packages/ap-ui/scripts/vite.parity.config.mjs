// Vite config for the parity fixture generator: the @alliancesoftware/ui package's own config with
// vanilla-extract's identifiers pinned to "debug" and the workspace Vite plugins resolved from source.
//
// The ui config calls `vanillaExtractPlugin()` without options, which picks short identifiers when
// Vite's mode is "production". Fixture normalisation and `css-mappings.json` rely on the debug form
// (`Button_baseButton__1a2b3c`), so this replaces that plugin instead of depending on the mode.
//
// The generator imports `extractMappingFromModule` from the vanilla-extract plugin's TypeScript
// source, which imports `@alliancesoftware/vite-plugin-django` by name. That package's entry points
// are build output (`dist/`), absent after a plain `yarn install` (as in CI), so the alias below
// resolves it to its source instead. The JS repo's own `types` field already points at `src/`.
//
// `syncHtmlUiParityFixtures.sh` sets AP_UI_UI_PACKAGE_DIR to the ui package directory.

import { createRequire } from "node:module";
import path from "node:path";
import { pathToFileURL } from "node:url";

const uiPackageDir = process.env.AP_UI_UI_PACKAGE_DIR;
if (!uiPackageDir) {
  throw new Error(
    "AP_UI_UI_PACKAGE_DIR must point to the @alliancesoftware/ui package"
  );
}
const uiRequire = createRequire(path.join(uiPackageDir, "package.json"));
const vitePackageDir = path.dirname(uiRequire.resolve("vite/package.json"));
const { loadConfigFromFile } = await import(
  pathToFileURL(path.join(vitePackageDir, "dist/node/index.js")).href
);
const { vanillaExtractPlugin } = uiRequire("@vanilla-extract/vite-plugin");

const WORKSPACE_SOURCE_ALIASES = [
  {
    find: "@alliancesoftware/vite-plugin-django",
    replacement: path.join(uiPackageDir, "../vite-plugin-django/src/index.ts"),
  },
];

function aliasEntries(alias) {
  if (!alias) {
    return [];
  }
  if (Array.isArray(alias)) {
    return alias;
  }
  return Object.entries(alias).map(([find, replacement]) => ({
    find,
    replacement,
  }));
}

export default async function parityConfig(configEnv) {
  const { config } = await loadConfigFromFile(
    configEnv,
    path.join(uiPackageDir, "vite.config.mjs")
  );
  return {
    ...config,
    plugins: [
      ...(config.plugins ?? [])
        .flat(Infinity)
        .filter((plugin) => plugin?.name !== "vanilla-extract"),
      vanillaExtractPlugin({ identifiers: "debug" }),
    ],
    resolve: {
      ...config.resolve,
      alias: [
        ...aliasEntries(config.resolve?.alias),
        ...WORKSPACE_SOURCE_ALIASES,
      ],
    },
  };
}
