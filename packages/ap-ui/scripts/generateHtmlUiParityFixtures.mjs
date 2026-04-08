#!/usr/bin/env node

import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { renderToStaticMarkup } from 'react-dom/server';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CASE_MODULES = [
    './parity_cases/button.mjs',
    './parity_cases/button_group.mjs',
];

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

async function generateFixtureFromModule(modulePath) {
    const caseModule = await import(new URL(modulePath, import.meta.url));
    const { component, cases } = caseModule;

    if (!component || !Array.isArray(cases)) {
        throw new Error(`Invalid parity case module at ${modulePath}`);
    }

    const serializedCases = [];
    for (const testCase of cases) {
        const { html, warnings } = captureWarnings(() => renderToStaticMarkup(testCase.buildElement()));
        serializedCases.push({
            name: testCase.name,
            template: testCase.template,
            expected_html: html,
            expected_warnings: warnings,
            meta: testCase.meta ?? {},
        });
    }

    const fixture = {
        generated_by: 'scripts/generateHtmlUiParityFixtures.mjs',
        generated_at_utc: new Date().toISOString(),
        component,
        styles: {},
        cases: serializedCases,
    };

    const fixturePath = path.resolve(__dirname, '../tests/fixtures', `ui_html_${component}_parity.json`);
    await fs.writeFile(fixturePath, `${JSON.stringify(fixture, null, 2)}\n`, 'utf8');
    return fixturePath;
}

async function main() {
    const onlyComponent = process.argv[2];
    const modulePaths = CASE_MODULES;
    for (const modulePath of modulePaths) {
        const caseModule = await import(new URL(modulePath, import.meta.url));
        if (onlyComponent && caseModule.component !== onlyComponent) {
            continue;
        }
        const fixturePath = await generateFixtureFromModule(modulePath);
        process.stdout.write(`Wrote ${fixturePath}\n`);
    }
}

await main();
