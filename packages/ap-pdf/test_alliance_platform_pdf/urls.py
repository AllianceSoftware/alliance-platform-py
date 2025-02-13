from alliance_platform.pdf.decorators import view_as_pdf
from django.urls import path

from .views import header_content_view
from .views import sample_html_view
from .views import simple_content_view
from .views import simple_content_view_spy

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
        view_as_pdf(optional=False, extra_headers={"X-Custom-Header": "custom-value"}, page_done_flag=None)(
            header_content_view
        ),
    ),
    path(
        "test-decorator-removes-header-set-to-none/",
        view_as_pdf(optional=False, extra_headers={"X-Custom-Header-Remove": None}, page_done_flag=None)(
            simple_content_view_spy
        ),
    ),
    path("dummy", sample_html_view),
]
