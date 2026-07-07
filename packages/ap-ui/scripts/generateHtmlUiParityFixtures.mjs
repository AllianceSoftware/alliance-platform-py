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
    './parity_cases/text_input.mjs',
    './parity_cases/number_input.mjs',
    './parity_cases/text_area.mjs',
    './parity_cases/table.mjs',
    './parity_cases/menubar.mjs',
];

const BUTTON_COMPONENTS = new Set(['button', 'button_group']);
const INPUT_COMPONENTS = new Set(['text_input', 'number_input', 'text_area']);
const TABLE_COMPONENTS = new Set(['table']);
const MENUBAR_COMPONENTS = new Set(['menubar']);

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

async function importBareModule(specifier) {
    try {
        // Prefer bare imports so vite-node resolves the same singletons as the component module graph.
        return await import(specifier);
    } catch {
        const uiRequire = await getUiRequire();
        return import(pathToFileURL(uiRequire.resolve(specifier)).href);
    }
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
    } else if (component === 'text_input') {
        components = {
            TextInput: await importDefault(path.join(uiPackageDir, 'components/text-input/TextInput.tsx')),
        };
    } else if (component === 'text_area') {
        components = {
            TextArea: await importDefault(path.join(uiPackageDir, 'components/text-input/TextArea.tsx')),
        };
    } else if (component === 'number_input') {
        components = {
            NumberInput: await importDefault(
                path.join(uiPackageDir, 'components/number-input/NumberInput.tsx')
            ),
        };
    } else if (component === 'table') {
        // Table itself comes from the ui package; the collection components (TableHeader etc.)
        // are the react-stately ones the ui package re-exports.
        const reactStately = await importBareModule('react-stately');
        components = {
            Table: await importDefault(path.join(uiPackageDir, 'components/table/Table.tsx')),
            ColumnHeaderLink: await importDefault(
                path.join(uiPackageDir, 'components/table/ColumnHeaderLink.tsx')
            ),
            TableHeader: reactStately.TableHeader,
            TableBody: reactStately.TableBody,
            Column: reactStately.Column,
            Row: reactStately.Row,
            Cell: reactStately.Cell,
        };
    } else if (component === 'menubar') {
        const Menubar = await importDefault(path.join(uiPackageDir, 'components/menu-bar/Menubar.tsx'));
        components = {
            Menubar,
            Item: Menubar.Item,
            SubMenu: Menubar.SubMenu,
            Section: Menubar.Section,
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

function normalizeClassTokens(classValue, allowedPrefixes, keepClassTokens) {
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
        if (keepClassTokens.has(token)) {
            return true;
        }
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

// React 18's server renderer emits some known camelCase DOM props verbatim (browsers treat
// attribute names case-insensitively). Lowercase them so fixtures match the HTML the Python
// renderer produces.
const CAMEL_CASE_ATTR_RE = /\s(autoComplete|inputMode|autoCorrect|autoCapitalize|spellCheck)=/g;
const REACT_ARIA_ID_RE = /react-aria-[^"'\s]+/g;

/**
 * Normalize react-aria generated ids into the deterministic ids the Python renderer emits.
 *
 * - `aria-labelledby` entries pointing at react-aria label ids are removed: the static renderer
 *   relies on the native `<label for>` association instead.
 * - `aria-describedby` entries pointing at react-aria ids that do not exist in the document are
 *   removed (react-aria reserves description/error slot ids during SSR even when nothing renders).
 *   Caller-supplied ids are always preserved.
 * - Remaining unreferenced react-aria element ids are dropped; the Python renderer only generates
 *   ids something else points at.
 * - Surviving react-aria ids are remapped, in order of first appearance, to the Python scheme
 *   `apui-<component>-<n>`.
 */
function normalizeReactAriaIds(html, component) {
    let normalized = html;
    normalized = normalized.replace(/\saria-labelledby="([^"]*)"/g, (_match, value) => {
        const tokens = value.split(/\s+/).filter(token => token && !token.startsWith('react-aria-'));
        return tokens.length ? ` aria-labelledby="${tokens.join(' ')}"` : '';
    });

    const presentIds = new Set();
    for (const match of normalized.matchAll(/\sid="(react-aria-[^"]*)"/g)) {
        presentIds.add(match[1]);
    }
    normalized = normalized.replace(/\saria-describedby="([^"]*)"/g, (_match, value) => {
        const tokens = value
            .split(/\s+/)
            .filter(token => token && (!token.startsWith('react-aria-') || presentIds.has(token)));
        return tokens.length ? ` aria-describedby="${tokens.join(' ')}"` : '';
    });

    const referencedIds = new Set();
    for (const match of normalized.matchAll(
        /\s(?:for|aria-controls|aria-errormessage)="(react-aria-[^"]*)"/g
    )) {
        referencedIds.add(match[1]);
    }
    for (const match of normalized.matchAll(/\saria-describedby="([^"]*)"/g)) {
        for (const token of match[1].split(/\s+/)) {
            if (token.startsWith('react-aria-')) {
                referencedIds.add(token);
            }
        }
    }
    normalized = normalized.replace(/\sid="(react-aria-[^"]*)"/g, (match, idValue) =>
        referencedIds.has(idValue) ? match : ''
    );

    const idMap = new Map();
    const idPrefix = `apui-${component.replaceAll('_', '-')}-`;
    normalized = normalized.replace(REACT_ARIA_ID_RE, token => {
        if (!idMap.has(token)) {
            idMap.set(token, `${idPrefix}${idMap.size + 1}`);
        }
        return idMap.get(token);
    });
    return normalized;
}

// React emits style declarations without spacing (`height:120px`); the Python renderer emits
// `height: 120px`. Normalize to the Python format.
function normalizeInlineStyleSpacing(html) {
    return html.replace(/\sstyle="([^"]*)"/g, (_match, value) => {
        const styleValue = value.replace(/:\s*/g, ': ').replace(/;\s*/g, '; ').trim();
        return ` style="${styleValue}"`;
    });
}

function normalizeInputComponentHtml(html, component) {
    let normalized = html;
    normalized = normalized.replace(CAMEL_CASE_ATTR_RE, (_match, name) => ` ${name.toLowerCase()}=`);
    normalized = normalizeReactAriaIds(normalized, component);
    normalized = normalizeInlineStyleSpacing(normalized);
    return normalized;
}

/**
 * Normalize the intentional differences between the React Aria table and the static renderer.
 *
 * The React Table is an interactive ARIA grid; the static table keeps native table semantics
 * instead (see the table components spec). Concretely:
 *
 * - Grid roles (`grid`/`row`/`rowgroup`/`columnheader`/`gridcell`), tab indexes and
 *   `aria-colindex`-style attributes are dropped; `role="rowheader"` is kept as the static
 *   renderer emits it too.
 * - `scope="col"` is added to header cells (native semantics; ARIA grids don't use scope).
 * - Sort link hrefs are absolute (built from the SSR currentUrl); the static renderer emits
 *   path-relative URLs.
 * - Generated hashes in CSS custom property names within style attributes are stripped, the same
 *   way class name hashes are.
 */
function normalizeTableComponentHtml(html, component) {
    let normalized = html;
    normalized = normalized.replace(/\srole="(grid|rowgroup|row|columnheader|gridcell)"/g, '');
    normalized = normalized.replace(/\stabindex="-?\d+"/g, '');
    normalized = normalized.replace(
        /\saria-(colindex|rowindex|colcount|rowcount|colspan|rowspan|multiselectable|selected)="[^"]*"/g,
        ''
    );
    // react-aria stamps collection bookkeeping attributes on every element; the static renderer
    // renders data-key only where the caller passes a key (covered by unit tests, not fixtures).
    normalized = normalized.replace(/\sdata-collection="[^"]*"/g, '');
    normalized = normalized.replace(/\sdata-key="[^"]*"/g, '');
    // The empty state row uses a raw JSX <td colSpan={...}> which the server renderer emits
    // verbatim; attribute names are case-insensitive in HTML.
    normalized = normalized.replace(/\s(colSpan|rowSpan)=/g, (_match, name) => ` ${name.toLowerCase()}=`);
    normalized = normalizeReactAriaIds(normalized, component);
    normalized = normalized.replace(/<th(?![\w-])/g, '<th scope="col"');
    normalized = normalized.replace(/href="http:\/\/testserver/g, 'href="');
    normalized = normalized.replace(/(--[\w-]+)__[a-z0-9]+\s*:/g, '$1:');
    normalized = normalizeInlineStyleSpacing(normalized);
    return normalized;
}

/**
 * Normalize the intentional differences between the React Menubar and the static renderer.
 *
 * - The offscreen overflow-measurement placeholders (the dummy "more items" node and any
 *   overflowed duplicates) are SSR'd for measuring; the static renderer has no overflow handling.
 * - Roving tabindex assignment is runtime state (dropped on both sides; unit tested).
 * - `data-key` is only rendered by the static renderer where the caller passes a key, and
 *   `data-collection` is react-aria bookkeeping.
 * - React renders `aria-disabled="false"` on enabled items and `aria-hidden="false"` on
 *   non-placeholder sections; the static renderer omits both.
 * - `hasLeadingIcon` (class + data attribute) is SSR'd optimistically as true and corrected
 *   client-side by `useHasChild`; the static renderer does not render it.
 * - Unreferenced react-aria element ids are dropped (the static renderer only generates ids
 *   something points at); surviving ids (section heading ids referenced from `aria-labelledby`)
 *   are remapped in order of first appearance to the deterministic static ids. Unlike the input
 *   components, `aria-labelledby` references must be preserved here.
 */
function normalizeMenubarComponentHtml(html, component) {
    let normalized = html;
    normalized = normalized.replace(
        /<li[^>]*data-key="____more_items_from_overflow"[\s\S]*?<\/li>/g,
        ''
    );
    normalized = normalized.replace(/\stabindex="-?\d+"/g, '');
    normalized = normalized.replace(/\sdata-key="[^"]*"/g, '');
    normalized = normalized.replace(/\sdata-collection="[^"]*"/g, '');
    normalized = normalized.replace(/\saria-disabled="false"/g, '');
    normalized = normalized.replace(/\saria-hidden="false"/g, '');
    normalized = normalized.replace(/\sdata-has-leading-icon="true"/g, '');
    normalized = normalized.replace(/\s?Menubar_hasLeadingIcon__\w+/g, '');

    const referencedIds = new Set();
    for (const match of normalized.matchAll(
        /\s(?:for|aria-controls|aria-labelledby|aria-describedby|aria-errormessage)="([^"]*)"/g
    )) {
        for (const token of match[1].split(/\s+/)) {
            if (token.startsWith('react-aria-')) {
                referencedIds.add(token);
            }
        }
    }
    normalized = normalized.replace(/\sid="(react-aria-[^"]*)"/g, (match, idValue) =>
        referencedIds.has(idValue) ? match : ''
    );

    const idMap = new Map();
    const idPrefix = `apui-${component.replaceAll('_', '-')}-`;
    normalized = normalized.replace(REACT_ARIA_ID_RE, token => {
        if (!idMap.has(token)) {
            idMap.set(token, `${idPrefix}${idMap.size + 1}`);
        }
        return idMap.get(token);
    });
    normalized = normalized.replace(/(--[\w-]+)__[a-z0-9]+\s*:/g, '$1:');
    normalized = normalizeInlineStyleSpacing(normalized);
    return normalized;
}

function normalizeDomAttributes(html, component, testCase, allowedPrefixes, keepClassTokens) {
    if (!html.trim()) {
        return '';
    }

    let normalized = html;
    normalized = normalized.replace(/\sdata-react-aria-pressable="true"/g, '');
    normalized = normalized.replace(/\stabindex="0"/g, '');
    if (BUTTON_COMPONENTS.has(component)) {
        normalized = normalized.replace(/\stype="button"/g, '');
        if (!testCase.template.includes('data-apui-slot="icon"')) {
            normalized = normalized.replace(/\sdata-icon-only="true"/g, '');
        }
    }
    if (INPUT_COMPONENTS.has(component)) {
        normalized = normalizeInputComponentHtml(normalized, component);
    }
    if (TABLE_COMPONENTS.has(component)) {
        normalized = normalizeTableComponentHtml(normalized, component);
    }
    if (MENUBAR_COMPONENTS.has(component)) {
        normalized = normalizeMenubarComponentHtml(normalized, component);
    }
    normalized = normalized.replace(/\sclass="([^"]*)"/g, (_match, classValue) => {
        const classTokens = normalizeClassTokens(classValue, allowedPrefixes, keepClassTokens);
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

function normalizeRenderedHtml(component, testCase, html, allowedPrefixes, keepClassTokens) {
    const normalized = normalizeDomAttributes(html, component, testCase, allowedPrefixes, keepClassTokens);
    if (component === 'button_group' && normalized) {
        return injectButtonGroupRuntime(normalized);
    }
    return normalized;
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
                currentUrl: new URL(currentUrl, 'http://testserver').toString(),
            };
        }
        const { html, warnings } = captureWarnings(() =>
            runtime.renderToStaticMarkup(
                testCase.buildElement({
                    React: runtime.React,
                    components: parityComponents,
                })
            )
        );
        if (currentUrl) {
            delete globalThis.globalSsrContext;
        }
        const normalizedHtml = normalizeRenderedHtml(
            component,
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
