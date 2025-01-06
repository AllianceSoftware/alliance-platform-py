from unittest import mock
from unittest import skipIf

from django.conf import settings
from django.http import HttpResponse
from django.test import TestCase
from django.test import override_settings
from django.urls import path

try:
    import playwright  # noqa

    playwright_installed = True
except ModuleNotFoundError:
    playwright_installed = False
    urlpatterns = []

if playwright_installed:
    from alliance_platform.pdf.decorators import view_as_pdf

    def simple_content_view(_):
        return HttpResponse("Simple content")

    def header_content_view(request):
        return HttpResponse(f"Header was: {request.META['X-Custom-Header']}")

    # This exists to spy on the simple_content_view, as I could not find a way
    # to mock.patch it from within a test case. Each test that needs this should
    # reset_mock() it
    simple_content_view_spy = mock.Mock(wraps=simple_content_view)

    urlpatterns = [
        path(
            "test-decorator-not-optional/",
            view_as_pdf(optional=False, page_done_flag=None)(simple_content_view),
        ),
        path(
            "test-decorator-optional-default-query-param/",
            view_as_pdf(page_done_flag=None)(simple_content_view),
        ),
        path(
            "test-decorator-optional-custom-query-param/",
            view_as_pdf(query_param_test="custom-pdf", page_done_flag=None)(simple_content_view),
        ),
        path(
            "test-decorator-optional-custom-query-test/",
            view_as_pdf(query_param_test=lambda r: "X-Custom-Header" in r.META, page_done_flag=None)(
                simple_content_view
            ),
        ),
        path(
            "test-decorator-response-uses-header/",
            view_as_pdf(
                optional=False, extra_headers={"X-Custom-Header": "custom-value"}, page_done_flag=None
            )(header_content_view),
        ),
        path(
            "test-decorator-removes-header-set-to-none/",
            view_as_pdf(optional=False, extra_headers={"X-Custom-Header-Remove": None}, page_done_flag=None)(
                simple_content_view_spy
            ),
        ),
    ]


def pdf_valid(data):
    # Very crude, just check if some basic header data is present
    return b"Creator (Chromium)" in data and b"PDF-1.4" in data


SAMPLE_HTML = "<html><body><p>Some content</p></body></html>"
# The rendered content of the PDF for SAMPLE_HTML should match this:
SAMPLE_PDF_CONTENTS = b".23999999 0 0 -.23999999 0 841.91998 cm\nq\n0 0 2479.1665 3507.7236 re\nW* n\nq\n3.1263134 0 0 3.1263134 0 0 cm\n1 1 1 RG 1 1 1 rg\n/G0 gs\n0 0 793 1122 re\nf\n0 0 0 RG 0 0 0 rg\nBT\n/F0 16 Tf\n1 0 0 -1 8 22 Tm\n<003600520050004800030046005200510057004800510057> Tj\nET\nQ\nQ\n"


@skipIf(not playwright_installed, "playwright not installed, skipping")
@override_settings(
    ROOT_URLCONF=__name__,
    MIDDLEWARE=[x for x in settings.MIDDLEWARE if "silk" not in x and "stronghold" not in x],
)
class DecoratorsTestCase(TestCase):
    def assert_simple_content_raw(self, response):
        self.assertEqual(200, response.status_code)
        self.assertEqual("text/html; charset=utf-8", response["Content-Type"])
        self.assertEqual(b"Simple content", response.content)

    def assert_simple_content_pdf(self, response):
        self.assertEqual(200, response.status_code)
        self.assertEqual("application/pdf", response["Content-Type"])
        self.assertTrue(pdf_valid(response.content))

    def test_decorator_not_optional(self):
        view_url = "/test-decorator-not-optional/"
        self.assert_simple_content_pdf(self.client.get(view_url))

    def test_decorator_optional_default_query_param(self):
        view_url = "/test-decorator-optional-default-query-param/"
        self.assert_simple_content_raw(self.client.get(view_url))
        self.assert_simple_content_raw(self.client.get(view_url, {"pdf": "false"}))
        self.assert_simple_content_pdf(self.client.get(view_url, {"pdf": "1"}))
        self.assert_simple_content_pdf(self.client.get(view_url, {"pdf": "true"}))

    def test_decorator_optional_custom_query_param(self):
        view_url = "/test-decorator-optional-custom-query-param/"
        self.assert_simple_content_raw(self.client.get(view_url))
        self.assert_simple_content_raw(self.client.get(view_url, {"pdf": "false"}))
        self.assert_simple_content_raw(self.client.get(view_url, {"pdf": "true"}))
        self.assert_simple_content_raw(self.client.get(view_url, {"custom-pdf": "false"}))
        self.assert_simple_content_pdf(self.client.get(view_url, {"custom-pdf": "true"}))

    def test_decorator_optional_custom_query_test(self):
        view_url = "/test-decorator-optional-custom-query-test/"
        self.assert_simple_content_raw(self.client.get(view_url))
        self.assert_simple_content_raw(self.client.get(view_url, {"pdf": "true"}))
        self.assert_simple_content_pdf(self.client.get(view_url, {}, **{"X-Custom-Header": "dummy"}))

    def test_decorator_custom_header(self):
        view_url = "/test-decorator-response-uses-header/"
        self.assert_simple_content_pdf(self.client.get(view_url))

    def test_decorator_custom_header_removed_if_none(self):
        view_url = "/test-decorator-removes-header-set-to-none/"
        simple_content_view_spy.reset_mock()

        self.assert_simple_content_pdf(
            self.client.get(
                view_url, {}, **{"X-Custom-Header-Remove": "dummy", "X-Custom-Header-Keep": "keep"}
            )
        )
        simple_content_view_spy.assert_called()
        request = simple_content_view_spy.call_args_list[0][0][0]
        self.assertNotIn("X-Custom-Header-Remove", request.META)
        self.assertEqual("keep", request.META["X-Custom-Header-Keep"])
