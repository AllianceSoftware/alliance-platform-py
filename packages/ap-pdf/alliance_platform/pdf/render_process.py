from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from typing import TYPE_CHECKING
from typing import Any

from asgiref.sync import sync_to_async
import django
from django.conf import settings
from django.http import parse_cookie
from django.http.request import HttpHeaders
from django.utils.module_loading import import_string
from playwright._impl._api_structures import SetCookieParam
from playwright.async_api import Route
from playwright.async_api import TimeoutError
from playwright.async_api import async_playwright

if TYPE_CHECKING:
    # When invoked as a CLI script python doesn't see this as being in a module.
    # sys.path is modified later to allow the module to be found but if we try to
    # import at this point it will fail
    from alliance_platform.pdf.request_handlers import RequestHandler


def logger():
    return logging.getLogger("alliance_platform.pdf")


def log(level, message):
    if __name__ == "__main__":
        sys.stderr.write(str(message).rstrip("\n") + "\n")
    else:
        getattr(logger(), level)(message)


async def handle_route(route: Route, handlers: list[RequestHandler]):
    # We import this here to allow same statement to work when run both directly and
    # as a sub-process
    from alliance_platform.pdf.request_handlers import RequestHandlerResponseStatus

    request = route.request

    for handler in handlers:
        response = await sync_to_async(handler.handle_request)(request)
        if response is None:
            continue

        log(
            "debug",
            "Network request: %s %s Status: %s\nHandled by: %s\n"
            % (
                request.method,
                request.url,
                response.status,
                handler.__class__.__name__,
            ),
        )

        if response.status == RequestHandlerResponseStatus.CONTINUE:
            return await route.continue_()
        if response.status == RequestHandlerResponseStatus.ABORT:
            return await route.abort()
        if response.status == RequestHandlerResponseStatus.SUCCESS:
            return await route.fulfill(**response.payload)

    log("error", "Unhandled request: %s %s" % (request.method, request.url))
    return await route.abort()


async def handle_route_wrapper(request: Route, handlers: list[RequestHandler]):
    try:
        return await handle_route(request, handlers)
    except Exception:
        import traceback

        traceback.print_exc()
    return await request.abort()


async def render_pdf(
    source_url: str,
    handlers: list[RequestHandler],
    meta: dict[str, str],
    page_done_flag: str | None = None,
    page_done_timeout_msecs: int = 10000,
    **pdf_options,
) -> bytes:
    """Render a page to PDF using playwright.

    :param source_url: url of a route to render
    :param handlers: a list of RequestHandler's (see request_handlers)
    :param meta: the request meta dict. This is used to extract any cookies that need to be set.
    :param page_done_flag: a javascript expression that, when evaluates as truthy, indicates
    the page has finished rendering
    :param page_done_timeout_msecs: wait up to this time in milliseconds for the page_done_flag
    to evaluate to a truthy value (implies page_done_flag has been set)
    **pdf_options: Any other params accepted by `Page.pdf() <https://playwright.dev/python/docs/next/api/class-page#page-pdf>`_

    :return: the rendered PDF byte data
    """
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=os.getenv("CHROMIUM_EXECUTABLE_PATH"))
        context = await browser.new_context()
        page = await context.new_page()
        original_headers = HttpHeaders(meta)
        raw_cookies = original_headers.get("cookie")
        if raw_cookies:
            cookies: list[SetCookieParam] = []
            for name, value in parse_cookie(raw_cookies).items():
                cookies.append({"url": source_url, "name": name, "value": value})
            await context.add_cookies(cookies)
        # This lets us intercept each request and decide what to do with it
        await page.route("**/*", lambda route: asyncio.ensure_future(handle_route_wrapper(route, handlers)))
        page.on("console", lambda message: log("debug", "console: %s" % message.text))

        await page.goto(source_url, wait_until="networkidle")

        if page_done_flag:
            try:
                await page.wait_for_function(page_done_flag, timeout=page_done_timeout_msecs)
            except TimeoutError:
                # Try rendering anyway
                pass

        await asyncio.sleep(0.5)

        data = await page.pdf(**pdf_options)
        await browser.close()
        return data


def create_handlers(_context: dict[str, Any]) -> list[RequestHandler]:
    """
    Create and initialize the request handlers (when running as a subprocess, these will be
    supplied as serialized dicts, and need to be de-serialized in this process.)
    :param _context: the context passed from the parent process.
    :return: a list of initialized request handlers
    """

    # An item in _context['handlers'] can be either a dict representing a serialized handler,
    # or a class instance if we are not running in a sub-process (for example when running tests)
    handlers = []
    for handler_data in _context["handlers"]:
        if isinstance(handler_data, dict):
            path = handler_data.pop("path")
            handler_class = import_string(path)
            handler = handler_class.deserialize(handler_data)
        else:
            handler = handler_data
        handler.setup(_context, log)
        handlers.append(handler)
    return handlers


def process_request(_context: dict[str, Any]) -> bytes:
    handlers = create_handlers(_context)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(
        render_pdf(
            _context["source_url"],
            handlers,
            _context.get("request_meta", {}),
            _context.get("page_done_flag"),
            _context.get("page_done_timeout_msecs", 10000),
            **_context.get("kwargs", {}),
        )
    )
    loop.close()
    return result


if __name__ == "__main__":
    # Entry point when run as a sub-process
    sys.path.insert(0, "")
    django.setup()
    setattr(settings, "_ALLIANCE_PLATFORM_PDF_PROCESS_ACTIVE", True)
    context = json.load(sys.stdin)
    data = process_request(context)
    sys.stdout.buffer.write(data)
