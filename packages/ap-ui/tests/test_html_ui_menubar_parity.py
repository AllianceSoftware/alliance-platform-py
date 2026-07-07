from __future__ import annotations

import re
from typing import Any
import warnings

from tests.parity.base import HtmlUIParityTestCase
from tests.parity.normalizers import normalize_html_fragment

# The static renderer produces extensions the React SSR output cannot contain: hidden popup
# wrappers for closed submenus (React portals/omits them), aria-controls/popup id wiring, the
# runtime bootstrap script and the state attributes it reads, roving tabindex assignment, explicit
# data-open="false"/type="button" on triggers and data-key/data-current markers. These are covered
# by unit tests (test_html_ui_menubar_components) and stripped here before comparison.

_RUNTIME_SCRIPT_RE = re.compile(r'<script type="module">.*?</script>', re.DOTALL)
_POPOVER_OPEN_TAG_RE = re.compile(r"<div\b[^>]*\bdata-apui-menu-popover\b[^>]*>")
_HIDDEN_INLINE_POPUP_OPEN_TAG_RE = re.compile(r"<ul\b[^>]*\bhidden\b[^>]*\bdata-apui-menu-popup\b[^>]*>")

_STATIC_ATTR_RES = [
    re.compile(r'\sdata-djid="[^"]*"'),
    re.compile(r"\sdata-apui-menu-submenu(?=[\s>])"),
    re.compile(r"\sdata-apui-menu-popup(?=[\s>])"),
    re.compile(r'\saria-controls="[^"]*"'),
    re.compile(r'\sid="apui-menu-[^"]*"'),
    re.compile(r'\sdata-open="false"'),
    re.compile(r'\sdata-current="true"'),
    re.compile(r'\sdata-open-class="[^"]*"'),
    re.compile(r'\sdata-focused-class="[^"]*"'),
    re.compile(r'\sdata-popover-open-class="[^"]*"'),
    re.compile(r'\sdata-should-focus-wrap="[^"]*"'),
    re.compile(r'\sdata-default-focused-key="[^"]*"'),
    re.compile(r'\stabindex="-?\d+"'),
    re.compile(r'\sdata-key="[^"]*"'),
    re.compile(r'\stype="button"'),
]

_TAG_SCANNERS = {
    "div": re.compile(r"<div\b|</div>", re.IGNORECASE),
    "ul": re.compile(r"<ul\b|</ul>", re.IGNORECASE),
}


def _strip_subtrees(html: str, open_tag_re: re.Pattern[str], tag_name: str) -> str:
    """Remove every element matched by ``open_tag_re`` including its (balanced) subtree."""
    scanner = _TAG_SCANNERS[tag_name]
    result: list[str] = []
    index = 0
    while True:
        match = open_tag_re.search(html, index)
        if match is None:
            result.append(html[index:])
            break
        result.append(html[index : match.start()])
        depth = 1
        pos = match.end()
        while depth:
            next_match = scanner.search(html, pos)
            if next_match is None:
                pos = len(html)
                break
            depth += -1 if next_match.group(0).startswith("</") else 1
            pos = next_match.end()
        index = pos
    return "".join(result)


def strip_static_menubar_extensions(value: str) -> str:
    normalized = _RUNTIME_SCRIPT_RE.sub("", value)
    # Closed flyout popovers and closed inline menus have no React SSR counterpart at all
    normalized = _strip_subtrees(normalized, _POPOVER_OPEN_TAG_RE, "div")
    normalized = _strip_subtrees(normalized, _HIDDEN_INLINE_POPUP_OPEN_TAG_RE, "ul")
    for attr_re in _STATIC_ATTR_RES:
        normalized = attr_re.sub("", normalized)
    return normalized


class UIMenubarParityTestCase(HtmlUIParityTestCase):
    fixture_component = "menubar"

    def assert_parity_case(self, case: dict[str, Any], context_kwargs: dict[str, Any] | None = None):
        with self.setup_render_context():
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                output = self.render_ui_template(case["template"], context_kwargs)

        actual_html = normalize_html_fragment(strip_static_menubar_extensions(output))
        expected_html = normalize_html_fragment(strip_static_menubar_extensions(case["expected_html"]))
        self.assertEqual(actual_html, expected_html)

        expected_warnings = case.get("expected_warnings", [])
        actual_warnings = [str(item.message) for item in caught_warnings]
        self.assertEqual(actual_warnings, expected_warnings)

    def test_fixture_cases(self):
        fixture = self.load_fixture()
        self.assertGreater(len(fixture["cases"]), 0)
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                self.assert_parity_case(case)
