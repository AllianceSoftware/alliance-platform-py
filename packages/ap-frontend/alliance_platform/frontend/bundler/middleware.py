import logging
import warnings

from django.http import HttpRequest
from django.http import HttpResponse

from .context import BundlerAssetContext

logger = logging.getLogger("alliance_platform.frontend")


class BundlerAssetContextMiddleware:
    """Middleware that wraps requests in a :class:`~alliance_platform.frontend.bundler.context.BundlerAssetContext` manager

    Within a Django request you can call :meth:`~alliance_platform.frontend.bundler.context.BundlerAssetContext.get_current` and
    it will return context instance for the current request. :class:`~alliance_platform.frontend.bundler.context.BundlerAssetContext`
    does this on init.

    This is currently only used to facilitate :ref:`server side rendering <ssr>` by collecting all the items that need to
    be rendered. This works as follows:

    - :class:`~alliance_platform.frontend.bundler.context.SSRItem` can be queued for server side rendering using
      :meth:`~alliance_platform.frontend.bundler.context.BundlerAssetContext.queue_ssr`. The caller (e.g. a template node) must
      render a placeholder element in the page, e.g. ``<!-- ___SSR_PLACEHOLDER_0___ -->`` - this placeholder string is
      returned by ``queue_ssr``
    - The middleware processes the request like normal so all the HTML is generated, including all the necessary placeholders.
    - It then does the SSR for all requested items.
    - For each item, it will replace the placeholder in the HTML with the rendered version.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        with BundlerAssetContext(request=request) as asset_context:
            response: HttpResponse = self.get_response(request)
            if not asset_context.requires_post_processing():
                # No ssr requests - can return response directly
                return response
            if response.has_header("content-type"):
                # Warn if SSR has been requested but response isn't HTML
                if not response.headers["content-type"].startswith("text/html"):
                    asset_context.abort_post_process()
                    warnings.warn(
                        f"There are items to SSR but the response is {response['content-type']} - items have been ignored"
                    )
                    return response
            response.content = asset_context.post_process(response.content.decode()).encode()

            return response
