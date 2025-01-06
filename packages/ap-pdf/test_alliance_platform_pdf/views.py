from unittest import mock

from django.http import HttpResponse

SAMPLE_HTML = """<html><body>
<svg xmlns="http://www.w3.org/2000/svg" width="467" height="462">
    <rect x="140" y="120" width="250" height="250" style="fill:#ffffff; stroke:#000000; stroke-width:2px;" />
</svg>
</body></html>"""


def simple_content_view(_):
    return HttpResponse("Simple content")


def header_content_view(request):
    return HttpResponse(f"Header was: {request.META['X-Custom-Header']}")


def sample_html_view(_):
    return HttpResponse(SAMPLE_HTML)


# This exists to spy on the simple_content_view, as I could not find a way
# to mock.patch it from within a test case. Each test that needs this should
# reset_mock() it

simple_content_view_spy = mock.Mock(wraps=simple_content_view)
