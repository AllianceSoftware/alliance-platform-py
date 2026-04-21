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
const BUTTON_SIZES = ['sm', 'md', 'lg', 'xl', '2xl'];
const DENSITIES = ['compact', 'xxs', 'xs', 'sm', 'md', 'lg', 'xl', 'xxl', 'xxxl'];
const BUTTON_CORE_CLASSES = new Set(['focus-ring-base', 'button-base', ...BUTTON_SIZES.map(size => `button-size-${size}`)]);
const BUTTON_GROUP_CLASSES = new Set([
    'button-group-base',
    'button-group-button-slot',
    'so-horizontal',
    'so-vertical',
    'so-align-start',
    'so-align-center',
    'so-align-end',
    ...DENSITIES.map(density => `so-density-${density}`),
]);

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

function canonicalizeClassToken(token) {
    if (!token) {
        return null;
    }

    if (token.startsWith('focusRing_base__')) {
        return 'focus-ring-base';
    }
    if (token.startsWith('Button_baseButton__')) {
        return 'button-base';
    }
    for (const size of BUTTON_SIZES) {
        if (token.startsWith(`Button_sizes_${size}__`)) {
            return `button-size-${size}`;
        }
    }
    if (token.startsWith('Button_sizes__')) {
        return null;
    }
    if (token.startsWith('ButtonGroup_buttonGroup__')) {
        return 'button-group-base';
    }
    if (token.startsWith('ButtonGroup_button__')) {
        return 'button-group-button-slot';
    }
    if (token.startsWith('SmartOrientation_container_horizontal__')) {
        return 'so-horizontal';
    }
    if (token.startsWith('SmartOrientation_container_vertical__')) {
        return 'so-vertical';
    }
    if (token.startsWith('SmartOrientation_align_start__')) {
        return 'so-align-start';
    }
    if (token.startsWith('SmartOrientation_align_center__')) {
        return 'so-align-center';
    }
    if (token.startsWith('SmartOrientation_align_end__')) {
        return 'so-align-end';
    }
    for (const density of DENSITIES) {
        if (token.startsWith(`SmartOrientation_density_${density}__`)) {
            return `so-density-${density}`;
        }
    }
    if (token.startsWith('SmartOrientation_containerBase__')) {
        return null;
    }
    if (token.includes('__')) {
        return null;
    }
    return token;
}

function normalizeClassTokens(classValue) {
    return dedupeTokens(
        tokenizeClasses(classValue)
            .map(token => canonicalizeClassToken(token))
            .filter(Boolean)
    );
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

function extractButtonSize(attrs, normalizedClassTokens) {
    const attrSize = attrs.get('data-size');
    if (typeof attrSize === 'string' && BUTTON_SIZES.includes(attrSize)) {
        return attrSize;
    }
    const classSize = normalizedClassTokens.find(token => token.startsWith('button-size-'));
    if (classSize) {
        return classSize.replace('button-size-', '');
    }
    return 'md';
}

function normalizeButtonElementHtml(
    html,
    {
        forceGroupSlotClass = false,
        keepIconOnly = false,
    } = {}
) {
    const elementMatch = html.match(/^<(button|a)\b([^>]*)>([\s\S]*)<\/\1>$/);
    if (!elementMatch) {
        return html;
    }

    const [, tagName, attrsString, childrenHtml] = elementMatch;
    const attrs = parseAttributes(attrsString);

    attrs.delete('data-react-aria-pressable');
    if (attrs.get('type') === 'button') {
        attrs.delete('type');
    }
    if (attrs.get('tabindex') === '0') {
        attrs.delete('tabindex');
    }
    if (!keepIconOnly) {
        attrs.delete('data-icon-only');
    }

    const normalizedClassTokens = normalizeClassTokens(attrs.get('class'));
    const size = extractButtonSize(attrs, normalizedClassTokens);
    const includeGroupSlotClass = forceGroupSlotClass || normalizedClassTokens.includes('button-group-button-slot');
    const customClassTokens = normalizedClassTokens.filter(
        token => !BUTTON_CORE_CLASSES.has(token) && token !== 'button-group-button-slot'
    );
    const classTokens = ['focus-ring-base', 'button-base', `button-size-${size}`];
    if (includeGroupSlotClass) {
        classTokens.push('button-group-button-slot');
    }
    classTokens.push(...customClassTokens);
    attrs.set('class', dedupeTokens(classTokens).join(' '));

    const orderedKeys = [
        'class',
        'data-apui',
        'data-variant',
        'data-color',
        'data-size',
        'data-shape',
        'data-icon-only',
        'data-disabled',
        'style',
        'href',
    ];
    return `<${tagName}${buildAttributesString(attrs, orderedKeys)}>${childrenHtml}</${tagName}>`;
}

function normalizeButtonHtml(testCase, html) {
    const keepIconOnly = testCase.template.includes('data-apui-slot="icon"');
    return normalizeButtonElementHtml(html, { keepIconOnly });
}

function normalizeButtonGroupHtml(testCase, html) {
    if (!html.trim()) {
        return '';
    }

    const rootMatch = html.match(/^<div\b([^>]*)>([\s\S]*)<\/div>$/);
    if (!rootMatch) {
        return html;
    }

    const [, attrsString, childrenRawHtml] = rootMatch;
    const attrs = parseAttributes(attrsString);
    const rootClassTokens = normalizeClassTokens(attrs.get('class'));
    const orientation = String(attrs.get('data-orientation') || 'horizontal');
    const align = String(attrs.get('data-align') || 'start');
    const density = String(attrs.get('data-density') || 'md');

    const customRootClasses = rootClassTokens.filter(token => !BUTTON_GROUP_CLASSES.has(token));
    attrs.set(
        'class',
        dedupeTokens([
            `so-${orientation}`,
            `so-align-${align}`,
            `so-density-${density}`,
            'button-group-base',
            ...customRootClasses,
        ]).join(' ')
    );
    attrs.set('data-orientation', orientation);
    attrs.set('data-djid', '__DJID__');

    const normalizedChildren = childrenRawHtml.replace(/<(button|a)\b[\s\S]*?<\/\1>/g, match => {
        const keepIconOnly = match.includes('data-apui-slot="icon"');
        return normalizeButtonElementHtml(match, {
            forceGroupSlotClass: true,
            keepIconOnly,
        });
    });

    const orderedKeys = ['class', 'data-apui', 'data-orientation', 'data-density', 'data-align', 'id', 'style', 'data-djid'];
    const rootHtml = `<div${buildAttributesString(attrs, orderedKeys)}>${normalizedChildren}</div>`;
    const scriptHtml =
        `<script type="module"> import attach from "${RUNTIME_ATTACH_IMPORT_URL}"; ` +
        `const el = document.querySelector("[data-djid='__DJID__']"); ` +
        'if (el) { attach(el); } </script>';
    return `${rootHtml}${scriptHtml}`;
}

function normalizeRenderedHtml(component, testCase, html) {
    if (component === 'button') {
        return normalizeButtonHtml(testCase, html);
    }
    if (component === 'button_group') {
        return normalizeButtonGroupHtml(testCase, html);
    }
    return html;
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
        const normalizedHtml = normalizeRenderedHtml(component, testCase, html);
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
