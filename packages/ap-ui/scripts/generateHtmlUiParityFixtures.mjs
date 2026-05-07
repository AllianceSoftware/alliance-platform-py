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
const RUNTIME_ATTACH_IMPORT_URL =
    'http://localhost:5273/static/@alliancesoftware/ui/components/layout/SmartOrientation.attach.ts';
let prettierFormatPromise;
const parityComponentRuntimeCache = new Map();
let uiRequirePromise;

async function fileExists(filePath) {
    try {
        await fs.access(filePath);
        return true;
    } catch {
        return false;
    }
}

async function resolveUiPackageJsonPath() {
    const explicitUiPackageDir = process.env.AP_UI_UI_PACKAGE_DIR;
    const explicitJsRepo = process.env.AP_UI_JS_REPO;

    const directCandidates = [];
    if (explicitUiPackageDir) {
        directCandidates.push(path.resolve(explicitUiPackageDir, 'package.json'));
    }
    if (explicitJsRepo) {
        directCandidates.push(path.resolve(explicitJsRepo, 'packages/ui/package.json'));
    }
    directCandidates.push(path.resolve(process.cwd(), 'package.json'));

    for (const packageJsonPath of directCandidates) {
        if (await fileExists(packageJsonPath)) {
            return packageJsonPath;
        }
    }

    const searchPaths = [];
    if (explicitUiPackageDir) {
        searchPaths.push(explicitUiPackageDir);
    }
    if (explicitJsRepo) {
        searchPaths.push(explicitJsRepo);
    }
    searchPaths.push(process.cwd());

    for (const searchPath of searchPaths) {
        try {
            return require.resolve('@alliancesoftware/ui/package.json', { paths: [searchPath] });
        } catch {
            // Keep trying subsequent resolution roots.
        }
    }

    return require.resolve('@alliancesoftware/ui/package.json');
}

async function loadRendererRuntime() {
    let reactModule;
    let reactDomServerModule;
    try {
        // Prefer bare imports so vite-node resolves the same React singleton for both
        // the component module graph and server renderer.
        reactModule = await import('react');
        reactDomServerModule = await import('react-dom/server');
    } catch {
        // Fallback for non-vite execution contexts.
        const uiPackageJsonPath = await resolveUiPackageJsonPath();
        const uiRequire = createRequire(uiPackageJsonPath);
        const reactPath = uiRequire.resolve('react');
        const reactDomServerPath = uiRequire.resolve('react-dom/server');
        reactModule = await import(pathToFileURL(reactPath).href);
        reactDomServerModule = await import(pathToFileURL(reactDomServerPath).href);
    }

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

async function resolveUiPackageDir() {
    const uiPackageJsonPath = await resolveUiPackageJsonPath();
    return path.dirname(uiPackageJsonPath);
}

async function getUiRequire() {
    if (!uiRequirePromise) {
        uiRequirePromise = resolveUiPackageJsonPath().then(uiPackageJsonPath => createRequire(uiPackageJsonPath));
    }
    return uiRequirePromise;
}

async function importDefault(modulePath) {
    const module = await import(pathToFileURL(modulePath).href);
    return module.default ?? module;
}

async function loadParityComponents(component) {
    if (parityComponentRuntimeCache.has(component)) {
        return parityComponentRuntimeCache.get(component);
    }

    const uiPackageDir = await resolveUiPackageDir();
    let components;
    if (component === 'button') {
        components = {
            Button: await importDefault(path.join(uiPackageDir, 'components/button/Button.tsx')),
        };
    } else if (component === 'button_group') {
        components = {
            Button: await importDefault(path.join(uiPackageDir, 'components/button/Button.tsx')),
            ButtonGroup: await importDefault(path.join(uiPackageDir, 'components/button/ButtonGroup.tsx')),
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
                const uiRequire = await getUiRequire();
                const prettierPath = uiRequire.resolve('prettier');
                const prettierModule = await import(pathToFileURL(prettierPath).href);
                return prettierModule.format ?? prettierModule.default?.format ?? null;
            } catch {
                try {
                    const prettierPath = require.resolve('prettier');
                    const prettierModule = await import(pathToFileURL(prettierPath).href);
                    return prettierModule.format ?? prettierModule.default?.format ?? null;
                } catch {
                    return null;
                }
            }
        })();
    }
    const prettierFormat = await prettierFormatPromise;
    if (!prettierFormat) {
        return content;
    }
    return prettierFormat(content, { parser: 'json' });
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

function dedupeTokens(tokens) {
    const seen = new Set();
    return tokens.filter(token => {
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
    return String(value)
        .trim()
        .split(/\s+/)
        .filter(Boolean);
}

function parseAttributes(attrString) {
    const attrs = new Map();
    const attrPattern = /([^\s=]+)(?:="([^"]*)")?/g;
    let match;
    while ((match = attrPattern.exec(attrString)) !== null) {
        attrs.set(match[1], match[2] ?? true);
    }
    return attrs;
}

function escapeAttribute(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('"', '&quot;');
}

function buildAttributesString(attrs, orderedKeys = []) {
    const parts = [];
    const consumed = new Set();

    const appendAttr = (name, value) => {
        if (value === null || value === undefined || value === false) {
            return;
        }
        if (value === true) {
            parts.push(` ${name}`);
        } else {
            parts.push(` ${name}="${escapeAttribute(value)}"`);
        }
    };

    for (const key of orderedKeys) {
        if (!attrs.has(key)) {
            continue;
        }
        consumed.add(key);
        appendAttr(key, attrs.get(key));
    }

    for (const [key, value] of attrs.entries()) {
        if (consumed.has(key)) {
            continue;
        }
        appendAttr(key, value);
    }

    return parts.join('');
}

function normalizeClassTokens(classValue, allowedPrefixes) {
    const normalized = [];
    for (const originalToken of tokenizeClasses(classValue)) {
        const hashIndex = originalToken.lastIndexOf('__');
        const hadHash = hashIndex !== -1;
        const token = hadHash ? originalToken.slice(0, hashIndex) : originalToken;
        if (!token) {
            continue;
        }

        if (token.includes('_')) {
            const prefix = token.split('_', 1)[0];
            if (hadHash && !allowedPrefixes.has(prefix)) {
                continue;
            }
        } else if (hadHash && !allowedPrefixes.has(token)) {
            continue;
        }
        normalized.push(token);
    }

    const deduped = dedupeTokens(normalized);
    return deduped.filter(token => {
        const hasChildToken = deduped.some(other => other !== token && other.startsWith(`${token}_`));
        if (hasChildToken) {
            return false;
        }
        if (token.endsWith('Base')) {
            const root = token.slice(0, -4);
            const hasRootChild = deduped.some(other => other !== token && other.startsWith(`${root}_`));
            if (hasRootChild) {
                return false;
            }
        }
        return true;
    });
}

function normalizeDomAttributes(html, testCase, allowedPrefixes) {
    if (!html.trim()) {
        return '';
    }

    let normalized = html;
    normalized = normalized.replace(/\sdata-react-aria-pressable="true"/g, '');
    normalized = normalized.replace(/\stabindex="0"/g, '');
    normalized = normalized.replace(/\stype="button"/g, '');
    if (!testCase.template.includes('data-apui-slot="icon"')) {
        normalized = normalized.replace(/\sdata-icon-only="true"/g, '');
    }
    normalized = normalized.replace(/\sclass="([^"]*)"/g, (_match, classValue) => {
        const classTokens = normalizeClassTokens(classValue, allowedPrefixes);
        return classTokens.length ? ` class="${classTokens.join(' ')}"` : '';
    });
    return normalized;
}

function injectButtonGroupRuntime(html) {
    const rootMatch = html.match(/^<div\b([^>]*)>([\s\S]*)<\/div>$/);
    if (!rootMatch) {
        return html;
    }

    const [, attrsString, childrenHtml] = rootMatch;
    const attrs = parseAttributes(attrsString);
    attrs.set('data-djid', '__DJID__');
    const rootHtml = `<div${buildAttributesString(attrs)}>${childrenHtml}</div>`;
    const scriptHtml =
        `<script type="module"> import attach from "${RUNTIME_ATTACH_IMPORT_URL}"; ` +
        `const el = document.querySelector("[data-djid='__DJID__']"); ` +
        'if (el) { attach(el); } </script>';
    return `${rootHtml}${scriptHtml}`;
}

function normalizeRenderedHtml(component, testCase, html, allowedPrefixes) {
    const normalized = normalizeDomAttributes(html, testCase, allowedPrefixes);
    if (component === 'button_group' && normalized) {
        return injectButtonGroupRuntime(normalized);
    }
    return normalized;
}

async function generateFixtureFromModule(modulePath, runtime) {
    const caseModule = await import(new URL(modulePath, import.meta.url));
    const { component, cases, class_prefixes: classPrefixes = [] } = caseModule;
    const allowedPrefixes = new Set(classPrefixes);
    const parityComponents = await loadParityComponents(component);

    if (!component || !Array.isArray(cases)) {
        throw new Error(`Invalid parity case module at ${modulePath}`);
    }

    const serializedCases = [];
    for (const testCase of cases) {
        const { html, warnings } = captureWarnings(() =>
            runtime.renderToStaticMarkup(
                testCase.buildElement({
                    React: runtime.React,
                    components: parityComponents,
                })
            )
        );
        const normalizedHtml = normalizeRenderedHtml(component, testCase, html, allowedPrefixes);
        serializedCases.push({
            name: testCase.name,
            template: testCase.template,
            expected_html: normalizedHtml,
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

    const serializedFixture = `${JSON.stringify(fixture, null, 2)}\n`;
    const formattedFixture = await formatFixtureJson(serializedFixture);
    await fs.writeFile(fixturePath, formattedFixture, 'utf8');
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
