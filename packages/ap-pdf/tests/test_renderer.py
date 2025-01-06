from io import BytesIO
import os
from unittest import mock
from unittest import skipIf

from django.conf import settings
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.test import TestCase
from django.test import override_settings
from django.urls import path
from django.views import View

try:
    import playwright  # noqa

    playwright_installed = True
except ModuleNotFoundError:
    playwright_installed = False

try:
    from pypdf import PdfReader

    pypdf_installed = True
except ImportError:
    pypdf_installed = False


if playwright_installed:
    from alliance_platform.pdf.render import render_pdf
    from alliance_platform.pdf.request_handlers import CustomRequestHandler
    from alliance_platform.pdf.request_handlers import MediaHttpRequestHandler
    from alliance_platform.pdf.request_handlers import StaticHttpRequestHandler

    class HugeLogRequestHandler(CustomRequestHandler):
        def handle_request(self, request):
            self.log("debug", "x" * 80000)
            return super().handle_request(request)


def get_page_contents(data):
    result = PdfReader(BytesIO(data))
    return result.pages[0].get_contents().get_data()


# Only render svg rather than text to avoid differences on platforms in text rendering
SAMPLE_HTML = """<html><body>
<svg xmlns="http://www.w3.org/2000/svg" width="467" height="462">
    <rect x="140" y="120" width="250" height="250" style="fill:#ffffff; stroke:#000000; stroke-width:2px;" />
</svg>
</body></html>"""
# The rendered content of the PDF for SAMPLE_HTML should match this:
SAMPLE_PDF_CONTENTS = b".23999999 0 0 -.23999999 0 841.91998 cm\nq\n25 25 1459.375 1443.75 re\nW* n\nq\n3.125 0 0 3.125 25 25 cm\n1 1 1 RG 1 1 1 rg\n/G3 gs\n140 120 250 250 re\nf\n0 0 0 RG 0 0 0 rg\n/G4 gs\n140 120 250 250 re\nS\nQ\nQ\n"
# The rendered content of the test_alliance_platform.pdf/template_<static|media>_file.html should match this:
TEMPLATE_PDF_CONTENTS = b".23999999 0 0 -.23999999 0 841.91998 cm\nq\n25 25 1459.375 1443.75 re\nW* n\nq\n3.125 0 0 3.125 25 25 cm\n1 1 1 RG 1 1 1 rg\n/G3 gs\n140 120 250 250 re\nf\n0 0 0 RG 0 0 0 rg\n/G4 gs\n140 120 250 250 re\nS\nQ\nQ\n"


class SampleView(View):
    def get(self, request, *args, **kwargs):
        return HttpResponse(SAMPLE_HTML)


urlpatterns = [path("dummy", SampleView.as_view())]


@skipIf(not pypdf_installed, "pypdf not installed, skipping")
@skipIf(not playwright_installed, "playwright not installed, skipping")
@override_settings(
    INSTALLED_APPS=["alliance_platform.pdf"],
    ROOT_URLCONF=__name__,
    MIDDLEWARE=[x for x in settings.MIDDLEWARE if "silk" not in x and "stronghold" not in x],
)
class RendererTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def render_pdf(self, **kwargs):
        data = render_pdf(run_as_subprocess=False, page_done_flag=None, **kwargs)
        return get_page_contents(data)

    def test_pdf_render_basic(self):
        contents = self.render_pdf(html=SAMPLE_HTML)
        self.assertEqual(SAMPLE_PDF_CONTENTS, contents)

    def test_pdf_render_custom_handler(self):
        url = "http://127.0.0.1/dummy"
        contents = self.render_pdf(
            url=url,
            request_handlers=[CustomRequestHandler({url: {"body": SAMPLE_HTML}})],
        )
        self.assertEqual(SAMPLE_PDF_CONTENTS, contents)

        # Check that trailing slashes are normalized
        contents = self.render_pdf(
            url=url + "/",
            request_handlers=[CustomRequestHandler({url: {"body": SAMPLE_HTML}})],
        )
        self.assertEqual(SAMPLE_PDF_CONTENTS, contents)

    @override_settings(STATICFILES_DIRS=[os.path.join(os.path.dirname(__file__), "static_files")])
    def test_pdf_render_handles_static_files(self):
        url = "http://127.0.0.1/dummy"
        static_handler = StaticHttpRequestHandler()
        with mock.patch.object(
            StaticHttpRequestHandler,
            "handle_request",
            wraps=static_handler.handle_request,
        ) as spy:
            contents = self.render_pdf(
                url=url,
                request_handlers=[
                    CustomRequestHandler(
                        {
                            url: {
                                "body": render_to_string(
                                    "test_alliance_platform_pdf/template_static_file.html",
                                )
                            }
                        }
                    ),
                    static_handler,
                ],
            )
            spy.assert_called()
            self.assertEqual(TEMPLATE_PDF_CONTENTS, contents)

    @override_settings(
        MEDIA_ROOT=os.path.join(os.path.dirname(__file__), "static_files"),
        MEDIA_URL="/custom-media/",
    )
    def test_pdf_render_handles_media_files(self):
        url = "http://127.0.0.1/dummy"
        media_handler = MediaHttpRequestHandler()
        with mock.patch.object(
            MediaHttpRequestHandler,
            "handle_request",
            wraps=media_handler.handle_request,
        ) as spy:
            contents = self.render_pdf(
                url=url,
                request_handlers=[
                    CustomRequestHandler(
                        {
                            url: {
                                "body": render_to_string(
                                    "test_alliance_platform_pdf/template_media_file.html",
                                )
                            }
                        }
                    ),
                    media_handler,
                ],
            )
            spy.assert_called()
            self.assertEqual(TEMPLATE_PDF_CONTENTS, contents)

    def test_pdf_render_huge_log_output(self):
        url = "http://127.0.0.1/dummy"
        with self.assertLogs("alliance_platform.pdf", level="DEBUG") as cm:
            data = render_pdf(
                run_as_subprocess=True,
                page_done_flag=None,
                url=url,
                request_handlers=[HugeLogRequestHandler({url: {"body": SAMPLE_HTML}})],
            )
            contents = get_page_contents(data)
            self.assertEqual(SAMPLE_PDF_CONTENTS, contents)

        log_size = len("".join(cm.output).encode("utf-8")) / 1024
        self.assertTrue(log_size > 64)

    def test_default_handlers(self):
        url = "http://127.0.0.1/dummy"
        data = render_pdf(
            run_as_subprocess=False,
            page_done_flag=None,
            url=url,
            request_headers={"HTTP_HOST": "127.0.0.1"},
        )
        contents = get_page_contents(data)
        self.assertEqual(SAMPLE_PDF_CONTENTS, contents)
