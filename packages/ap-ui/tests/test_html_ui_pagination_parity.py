from __future__ import annotations

import re
from typing import Any

from django.test import RequestFactory

from tests.parity.base import HtmlUIParityTestCase

# The static renderer precomputes the item ranges React picks from the rendered width: the
# configured counts (large) plus the 620px and 450px breakpoint ranges (medium, small), each item
# marked with its range in data-responsive-range. React's SSR output has the configured counts only.
_SMALLER_RANGE_ITEM_RE = re.compile(
    r'<li\b[^>]*\sdata-responsive-range="(?:medium|small)"[^>]*>.*?</li>',
    re.DOTALL,
)
_LARGE_RANGE_ATTRIBUTE_RE = re.compile(r'\sdata-responsive-range="large"')
# Disabled links have no href; the static renderer also gives them tabindex="-1".
_DISABLED_LINK_RE = re.compile(r'<a\b[^>]*\saria-disabled="true"[^>]*>')


def strip_static_pagination_extensions(value: str) -> str:
    normalized = _SMALLER_RANGE_ITEM_RE.sub("", value)
    normalized = _LARGE_RANGE_ATTRIBUTE_RE.sub("", normalized)
    return _DISABLED_LINK_RE.sub(lambda match: match.group(0).replace(' tabindex="-1"', ""), normalized)


class UIPaginationParityTestCase(HtmlUIParityTestCase):
    fixture_component = "pagination"

    request_factory = RequestFactory()

    def normalize_static_html(self, html: str, fixture: dict[str, Any]) -> str:
        return strip_static_pagination_extensions(super().normalize_static_html(html, fixture))

    def test_fixture_cases(self):
        fixture = self.load_fixture()
        self.assertGreater(len(fixture["cases"]), 0)
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                # React builds its links from the URL the case records; the static renderer builds
                # them from the request.
                request = self.request_factory.get(case["meta"]["current_url"])
                self.assert_parity_case(case, {"request": request})
