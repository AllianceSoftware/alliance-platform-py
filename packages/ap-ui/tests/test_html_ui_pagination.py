from __future__ import annotations

from html import unescape
import re
from typing import Any
import warnings

from django.test import RequestFactory

from tests.parity.base import HtmlUIParityTestCase


class UIPaginationRendererTestCase(HtmlUIParityTestCase):
    def render_with_warnings(
        self,
        template_body: str,
        context_kwargs: dict[str, Any] | None = None,
    ) -> tuple[str, list[str]]:
        with self.setup_render_context():
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                output = self.render_ui_template(template_body, context_kwargs)
        return output, [str(item.message) for item in caught_warnings]

    def get_link(self, output: str, aria_label: str) -> str:
        match = re.search(rf'<a[^>]*aria-label="{re.escape(aria_label)}"[^>]*>', output)
        if match is None:
            self.fail(f"No link found with aria-label={aria_label!r}")
        return unescape(match.group(0))

    def get_responsive_range_html(self, output: str, visibility: str) -> str:
        return "".join(
            re.findall(
                rf'<li class="[^"]*Pagination_responsiveItemVisibility_{visibility}[^"]*">(.*?)</li>',
                output,
                flags=re.DOTALL,
            )
        )

    def get_page_numbers(self, output: str, visibility: str) -> list[int]:
        range_html = self.get_responsive_range_html(output, visibility)
        return [
            int(page)
            for page in re.findall(r'aria-label="(?:Go to page|Current Page, Page) (\d+)"', range_html)
        ]

    def assert_warning_contains(self, caught: list[str], expected: str) -> None:
        self.assertTrue(
            any(expected in message for message in caught),
            f"No warning contained {expected!r}: {caught!r}",
        )

    def test_first_middle_and_last_page_ranges_match_react_algorithm(self):
        for page, expected_ranges in (
            (
                1,
                {
                    "large": ([1, 2, 3, 4, 5, 6, 100], 1),
                    "medium": ([1, 2, 3, 4, 100], 1),
                    "small": ([1, 2, 3], 0),
                },
            ),
            (
                50,
                {
                    "large": ([1, 48, 49, 50, 51, 52, 100], 2),
                    "medium": ([1, 49, 50, 51, 100], 2),
                    "small": ([49, 50, 51], 0),
                },
            ),
            (
                100,
                {
                    "large": ([1, 95, 96, 97, 98, 99, 100], 1),
                    "medium": ([1, 97, 98, 99, 100], 1),
                    "small": ([98, 99, 100], 0),
                },
            ),
        ):
            with self.subTest(page=page):
                output, caught = self.render_with_warnings(
                    '{% ui "pagination" page=page total=1000 page_size=10 '
                    'aria_label="Pagination" %}{% endui %}',
                    {"page": page},
                )

                self.assertEqual(caught, [])
                for visibility, (expected_pages, ellipsis_count) in expected_ranges.items():
                    with self.subTest(page=page, visibility=visibility):
                        range_html = self.get_responsive_range_html(output, visibility)
                        self.assertEqual(self.get_page_numbers(output, visibility), expected_pages)
                        self.assertEqual(range_html.count("Pagination_ellipsisButton"), ellipsis_count)
                self.assertIn(f'aria-label="Current Page, Page {page}"', output)
                self.assertIn('aria-current="page"', output)

        first_output, _ = self.render_with_warnings(
            '{% ui "pagination" page=1 total=1000 aria_label="Pagination" %}{% endui %}'
        )
        last_output, _ = self.render_with_warnings(
            '{% ui "pagination" page=100 total=1000 aria_label="Pagination" %}{% endui %}'
        )
        self.assertNotIn("href=", self.get_link(first_output, "Previous Page"))
        self.assertNotIn("href=", self.get_link(last_output, "Next Page"))

    def test_boundary_and_sibling_counts_control_range(self):
        output, caught = self.render_with_warnings(
            '{% ui "pagination" page=50 total=1000 page_size=10 boundary_count=2 '
            'sibling_count=1 aria_label="Pagination" %}{% endui %}'
        )

        self.assertEqual(caught, [])
        self.assertEqual(self.get_page_numbers(output, "large"), [1, 2, 49, 50, 51, 99, 100])
        self.assertEqual(self.get_page_numbers(output, "medium"), [1, 49, 50, 51, 100])
        self.assertEqual(self.get_page_numbers(output, "small"), [49, 50, 51])
        self.assertEqual(
            self.get_responsive_range_html(output, "large").count("Pagination_ellipsisButton"), 2
        )

    def test_total_zero_still_renders_one_current_page(self):
        output, caught = self.render_with_warnings(
            '{% ui "pagination" page=1 total=0 aria_label="Pagination" %}{% endui %}'
        )

        self.assertEqual(caught, [])
        for visibility in ("large", "medium", "small"):
            self.assertEqual(self.get_page_numbers(output, visibility), [1])
        self.assertIn('aria-label="Current Page, Page 1"', output)
        self.assertIn('aria-current="page"', output)
        self.assertIn('aria-disabled="true"', self.get_link(output, "Previous Page"))
        self.assertIn('aria-disabled="true"', self.get_link(output, "Next Page"))

    def test_links_preserve_request_query_and_page_one_removes_page_param(self):
        request = RequestFactory().get(
            "/reports/",
            {"status": "open", "tag": ["a", "b"], "page": 3, "pageSize": 50},
        )
        output, caught = self.render_with_warnings(
            '{% ui "pagination" page=3 total=100 page_size=10 aria_label="Pagination" %}{% endui %}',
            {"request": request},
        )

        self.assertEqual(caught, [])
        page_one = self.get_link(output, "Go to page 1")
        page_four = self.get_link(output, "Go to page 4")
        self.assertIn('href="/reports/?status=open&tag=a&tag=b"', page_one)
        self.assertIn('href="/reports/?status=open&tag=a&tag=b&page=4"', page_four)
        self.assertNotIn("pageSize", output)

    def test_custom_query_param_names_are_used(self):
        request = RequestFactory().get(
            "/reports/",
            {"p": 2, "limit": 25, "search": "active", "page": 9},
        )
        output, caught = self.render_with_warnings(
            '{% ui "pagination" page=2 total=100 page_size=25 page_query_param="p" '
            'page_size_query_param="limit" aria_label="Pagination" %}{% endui %}',
            {"request": request},
        )

        self.assertEqual(caught, [])
        self.assertIn('href="/reports/?search=active&page=9"', self.get_link(output, "Go to page 1"))
        self.assertIn(
            'href="/reports/?p=3&search=active&page=9"',
            self.get_link(output, "Go to page 3"),
        )
        self.assertNotIn("limit=", output)

    def test_variant_size_root_attributes_and_button_classes(self):
        output, caught = self.render_with_warnings(
            '{% ui "pagination" page=2 total=30 variant="compact" size="md" '
            'class_name="custom-pagination" style=style aria_label="Result pages" '
            'aria_describedby="page-help" data_testid="pager" %}{% endui %}',
            {"style": {"maxWidth": "40rem"}},
        )

        self.assertEqual(caught, [])
        self.assertIn(
            '<nav aria-label="Result pages" aria-describedby="page-help" data-testid="pager" '
            'class="Pagination_pagination_compact custom-pagination" style="max-width: 40rem">',
            output,
        )
        self.assertIn("focusRing_base Button_baseButton Button_sizes_md Pagination_prevButton", output)
        self.assertIn('data-variant="outlined"', output)
        self.assertIn('data-color="gray"', output)
        self.assertIn('data-size="md"', output)
        self.assertIn('data-apui-slot="icon"', output)
        self.assertEqual(output.count("<svg"), 2)

    def test_disabled_pagination_links_are_inert_without_javascript(self):
        output, caught = self.render_with_warnings(
            '{% ui "pagination" page=2 total=30 is_disabled=True aria_label="Pagination" %}{% endui %}'
        )

        self.assertEqual(caught, [])
        links = re.findall(r"<a[^>]*>", output)
        self.assertGreater(len(links), 2)
        for link in links:
            with self.subTest(link=link):
                self.assertNotIn("href=", link)
                self.assertIn('aria-disabled="true"', link)
                self.assertIn('tabindex="-1"', link)
                self.assertIn('data-disabled="true"', link)

    def test_missing_and_invalid_values_warn_with_safe_fallbacks(self):
        missing_output, missing_warnings = self.render_with_warnings(
            '{% ui "pagination" aria_label="Pagination" %}{% endui %}'
        )
        self.assertEqual(missing_output, "")
        self.assertEqual(missing_warnings, ["'pagination' requires a 'total' prop and will not render"])

        output, caught = self.render_with_warnings(
            '{% ui "pagination" total=-1 page=0 page_size=0 boundary_count=-1 sibling_count=-1 '
            'variant="large" size="lg" page_query_param="" page_size_query_param="" '
            'aria_label="Pagination" %}{% endui %}'
        )
        for prop_name in (
            "total",
            "page",
            "pageSize",
            "boundaryCount",
            "siblingCount",
            "variant",
            "size",
            "pageQueryParam",
            "pageSizeQueryParam",
        ):
            with self.subTest(prop_name=prop_name):
                self.assert_warning_contains(caught, f"Invalid '{prop_name}' prop passed")
        for visibility in ("large", "medium", "small"):
            self.assertEqual(self.get_page_numbers(output, visibility), [1])
        self.assertIn("Pagination_pagination_default", output)
        self.assertIn("Button_sizes_sm", output)

    def test_page_above_total_is_clamped_with_warning(self):
        output, caught = self.render_with_warnings(
            '{% ui "pagination" page=9 total=25 page_size=10 aria_label="Pagination" %}{% endui %}'
        )

        self.assertEqual(
            caught,
            ["Prop 'page' (9) exceeds the total page count (3); page 3 will be rendered"],
        )
        self.assertIn('aria-label="Current Page, Page 3"', output)

    def test_behavioral_props_warn_and_are_not_silently_rendered(self):
        output, caught = self.render_with_warnings(
            '{% ui "pagination" total=100 is_page_size_selectable=True page_sizes=page_sizes '
            "on_page_change=callback state=state render_item=callback breakpoints=breakpoints "
            'aria_label="Pagination" %}{% endui %}',
            {
                "page_sizes": [10, 20],
                "callback": lambda value: value,
                "state": {"page": 1},
                "breakpoints": {450: {"siblingCount": 1, "boundaryCount": 0}},
            },
        )

        self.assertIn("<nav", output)
        self.assert_warning_contains(
            caught,
            "Prop 'isPageSizeSelectable' will be ignored: page-size selection requires",
        )
        self.assert_warning_contains(
            caught,
            "Prop 'onPageChange' will be ignored: callback pagination is not supported",
        )
        self.assert_warning_contains(
            caught,
            "Prop 'state' will be ignored: client-managed pagination state is not supported",
        )
        self.assert_warning_contains(
            caught,
            "Prop 'renderItem' will be ignored: custom item render functions are not supported",
        )
        self.assert_warning_contains(
            caught,
            "Prop 'breakpoints' will be ignored: custom breakpoint configuration is not supported",
        )

    def test_resources_and_collected_document_keep_icons_inline(self):
        with self.setup_render_context() as asset_context:
            output = self.render_ui_document(
                '{% ui "pagination" page=2 total=30 aria_label="Pagination" %}{% endui %}'
            )
            resource_paths = [str(resource.path) for resource in asset_context.get_resources_for_bundling()]

        for expected in (
            "@alliancesoftware/ui/components/pagination/Pagination.css.ts",
            "@alliancesoftware/ui/components/button/Button.css.ts",
            "@alliancesoftware/ui/styles/base/focusRing.css.ts",
            "@alliancesoftware/icons/Icon.css.ts",
            "static-svg/outlined/ArrowLeftOutlined.svg",
            "static-svg/outlined/ArrowRightOutlined.svg",
        ):
            with self.subTest(resource=expected):
                self.assertTrue(any(path.endswith(expected) for path in resource_paths))
        self.assertEqual(output.count("<svg"), 2)
        self.assertNotIn("<img", output)
        self.assertIn("Pagination.css.ts", output)
        self.assertIn("Button.css.ts", output)
        self.assertIn("Icon.css.ts", output)

    def test_capture_can_render_as_static_table_footer_content(self):
        template = (
            '{% ui "pagination" page=1 total=30 aria_label="Pagination" as pagination %}{% endui %}'
            '{% ui "table" aria_label="Users" footer=pagination %}'
            '{% ui "table_header" %}{% ui "table_column" %}Name{% endui %}{% endui %}'
            '{% ui "table_body" %}{% endui %}'
            "{% endui %}"
        )
        output, caught = self.render_with_warnings(template)

        self.assertEqual(caught, [])
        self.assertIn('data-has-footer="true"', output)
        self.assertIn('<nav aria-label="Pagination"', output)
        self.assertNotIn("&lt;nav", output)
