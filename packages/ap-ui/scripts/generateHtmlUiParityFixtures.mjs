#!/usr/bin/env node

import fs from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { pathToFileURL } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CASE_MODULES = [
    './parity_cases/button.mjs',
    './parity_cases/button_group.mjs',
];

const require = createRequire(import.meta.url);
const GENERATED_AT_ENV_VAR = 'AP_UI_PARITY_GENERATED_AT_UTC';

async function loadRendererRuntime() {
    const uiPackageJsonPath = require.resolve('@alliancesoftware/ui/package.json');
    const uiRequire = createRequire(uiPackageJsonPath);

    const reactPath = uiRequire.resolve('react');
    const reactDomServerPath = uiRequire.resolve('react-dom/server');

    const reactModule = await import(pathToFileURL(reactPath).href);
    const reactDomServerModule = await import(pathToFileURL(reactDomServerPath).href);

    const React = reactModule.default ?? reactModule;
    const renderToStaticMarkup =
        reactDomServerModule.renderToStaticMarkup ?? reactDomServerModule.default?.renderToStaticMarkup;

    if (!React?.createElement || typeof renderToStaticMarkup !== 'function') {
        throw new Error(
            'Failed to load React rendering runtime. Ensure this script is run under a TS-aware runtime (for example vite-node).'
        );
    }

    return { React, renderToStaticMarkup };
}

async function loadExistingGeneratedAtUtc(fixturePath) {
    try {
        const existingRaw = await fs.readFile(fixturePath, 'utf8');
        const existingFixture = JSON.parse(existingRaw);
        if (typeof existingFixture.generated_at_utc === 'string' && existingFixture.generated_at_utc.length > 0) {
            return existingFixture.generated_at_utc;
        }
    } catch {
        // Ignore missing/invalid fixture and fall back to a generated timestamp.
    }
    return null;
}

function captureWarnings(run) {
    const warnings = [];
    const originalWarn = console.warn;
    console.warn = (...args) => {
        warnings.push(args.map(String).join(' '));
    };
    try {
        const html = run();
        return { html, warnings };
    } finally {
        console.warn = originalWarn;
    }
}

async function generateFixtureFromModule(modulePath, runtime) {
    const caseModule = await import(new URL(modulePath, import.meta.url));
    const { component, cases } = caseModule;

    if (!component || !Array.isArray(cases)) {
        throw new Error(`Invalid parity case module at ${modulePath}`);
    }

    const serializedCases = [];
    for (const testCase of cases) {
        const { html, warnings } = captureWarnings(() =>
            runtime.renderToStaticMarkup(testCase.buildElement({ React: runtime.React }))
        );
        serializedCases.push({
            name: testCase.name,
            template: testCase.template,
            expected_html: html,
            expected_warnings: warnings,
            meta: testCase.meta ?? {},
        });
    }

    const fixturePath = path.resolve(__dirname, '../tests/fixtures', `ui_html_${component}_parity.json`);
    const generatedAtUtc =
        process.env[GENERATED_AT_ENV_VAR] ?? (await loadExistingGeneratedAtUtc(fixturePath)) ?? new Date().toISOString();

    const fixture = {
        generated_by: 'scripts/generateHtmlUiParityFixtures.mjs',
        generated_at_utc: generatedAtUtc,
        component,
        styles: {},
        cases: serializedCases,
    };

    await fs.writeFile(fixturePath, `${JSON.stringify(fixture, null, 2)}\n`, 'utf8');
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
