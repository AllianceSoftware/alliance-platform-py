import json
import logging
import os
import subprocess
import sys
import tempfile

from alliance_platform.pdf.render_process import process_request
from alliance_platform.pdf.request_handlers import CustomRequestHandler
from alliance_platform.pdf.request_handlers import DjangoRequestHandler
from alliance_platform.pdf.request_handlers import MediaHttpRequestHandler
from alliance_platform.pdf.request_handlers import PassThroughRequestHandler
from alliance_platform.pdf.request_handlers import RequestHandler
from alliance_platform.pdf.request_handlers import StaticHttpRequestHandler
from alliance_platform.pdf.request_handlers import WhitelistDomainRequestHandler
from alliance_platform.pdf.settings import ap_pdf_settings
from django.conf import settings

try:
    from alliance_platform.frontend.bundler import get_bundler
    from alliance_platform.frontend.bundler.vite import ViteBundler

    AP_FRONTEND_INSTALLED = True
except ImportError:
    AP_FRONTEND_INSTALLED = False


RENDERER_PROCESS = os.path.abspath(os.path.join(os.path.dirname(__file__), "render_process.py"))


class PDFRendererException(Exception):
    """Errors in PDF rendering will be communicated via this exception type."""


def get_default_handlers() -> list[RequestHandler]:
    """Returns the default request handlers to use

    Includes :class:`~alliance_platform.pdf.request_handlers.StaticHttpRequestHandler`, :class:`~alliance_platform.pdf.request_handlers.MediaHttpRequestHandler`,
    :class:`~alliance_platform.pdf.request_handlers.DjangoRequestHandler` and :class:`~alliance_platform.pdf.request_handlers.WhitelistDomainRequestHandler`.

    :class:`~alliance_platform.pdf.request_handlers.WhitelistDomainRequestHandler` will use domains in the :py:attr:`~alliance_platform.pdf.settings.AlliancePlatformPDFSettingsType.WHITELIST_DOMAINS`
    setting and, when ``DEBUG=True``, also include the Vite dev server URL as extracted from the stats file.
    """

    whitelist_domains = [*ap_pdf_settings.WHITELIST_DOMAINS]
    if AP_FRONTEND_INSTALLED:
        bundler = get_bundler()
        if isinstance(bundler, ViteBundler) and bundler.is_development():
            whitelist_domains.append(bundler.dev_server_url)

    default_request_handlers = [
        StaticHttpRequestHandler(),
        MediaHttpRequestHandler(),
        DjangoRequestHandler(),
        WhitelistDomainRequestHandler(whitelist_domains),
    ]

    return default_request_handlers


def render_pdf(
    url: str | None = None,
    html: str | None = None,
    request_headers: dict[str, str] | None = None,
    request_handlers: list[RequestHandler] | None = None,
    pass_through: bool = False,
    run_as_subprocess: bool = True,
    page_done_flag: str | None = "window.__PAGE_RENDERING_FINISHED",
    page_done_timeout_msecs: int = 10000,
    pdf_options={"width": "210mm", "height": "297mm", "print_background": True},
):
    """Render a PDF from either a URL or directly from HTML

    Args:
        url: A url to render as a pdf. If the html argument is supplied, this argument will
            control the url that chromium sees as the 'source url', but the content will be determined
            by the html argument.
        html: HTML content to render as a pdf. If url is also supplied, the html content
            will appear to originate from the supplied url.
        request_headers: A dictionary of headers which are then passed through on network
            requests triggered when rendering the pdf.
        request_handlers: A list of RequestHandler's that will handle network requests
            triggered when rendering the pdf. Note that the order of these handlers is important: handlers
            are attempted in order until one returns a response or throws an error.
            If not specified uses return value of :meth:`~alliance_platform.pdf.render.get_default_handlers`.
        pass_through: If True, requests that aren't handled by any other request handler will
            be handled by the client. If False, requests that aren't handled by any other request handler will
            raise an exception.
        run_as_subprocess: Default is to run the playwright script as a subprocess. Set this to
            :code:`False` to run it in the current process. This is only used to support running tests currently.
        page_done_flag: Set this to an in-page variable that is used (in addition to waiting for page load
            and no more active network requests) that flags when a page has finished rendering. The script will
            wait up to page_done_timeout_msecs milliseconds for this flag to become truthy, and then continue
            rendering regardless. Set it to None to avoid this extra delay.
        page_done_timeout_msecs: Set this to the maximum time to wait for the :code:`page_done_flag` to
            become truthy.
        pdf_options: kwargs to be passed directly to `Page.pdf() <https://playwright.dev/python/docs/next/api/class-page#page-pdf>`_.
            the_default_options_are :code:`{ 'width': "210_mm", 'height': '297_mm', 'print_background': true }`.
    """

    if not url and not html:
        raise ValueError("One of url or html must be supplied")

    if getattr(settings, "_ALLIANCE_PLATFORM_PDF_PROCESS_ACTIVE", False):
        # The render_process sets this setting while it is running. A url config like:
        # urlpatterns = [
        #   url('test-pdf', lambda r: render_pdf(r)),
        # ]
        # for example will infinitely recurse if we don't stop this here.
        # Not set in package settings because it is only defined and used by internally running
        # processes - we don't want to set or document it in package setup
        raise PDFRendererException(
            "Recursive PDF renderer call detected. Ensure that any requests that are being "
            "handled by DjangoRequestHandler are not recursively calling render_pdf. Aborting."
        )

    handlers = get_default_handlers() if request_handlers is None else request_handlers

    if html:
        url = url or "http://dummy-url"
        handlers.insert(0, CustomRequestHandler({url: {"body": html}}))

    if pass_through:
        handlers.append(PassThroughRequestHandler())

    context = {
        "source_url": url,
        "handlers": ([handler.serialize() for handler in handlers] if run_as_subprocess else handlers),
        "request_meta": request_headers or {},
        "page_done_flag": page_done_flag,
        "page_done_timeout_msecs": page_done_timeout_msecs,
        "kwargs": pdf_options,
    }

    if run_as_subprocess:
        with tempfile.TemporaryFile("w+") as temp:
            json.dump(context, temp)
            temp.seek(0)

            pdf = subprocess.run(
                [sys.executable, RENDERER_PROCESS],
                stdin=temp,
                capture_output=True,
            )

            if pdf.returncode:
                raise PDFRendererException(pdf.stderr.decode("utf-8"))
            else:
                # Output any collected logging from the sub-process
                logging.getLogger("alliance_platform.pdf").debug(pdf.stderr.decode("utf-8"))

            return pdf.stdout

    # Not running as a sub-process
    return process_request(context)
