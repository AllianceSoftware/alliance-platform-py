from enum import Enum
from typing import cast
from urllib.parse import parse_qs
from urllib.parse import urlparse

from alliance_platform.pdf.utils import get_response_from_fullpath
from alliance_platform.pdf.utils import get_response_from_path
from alliance_platform.pdf.utils import get_static_roots
from alliance_platform.pdf.utils import get_static_url
from django.conf import settings
from django.core.handlers.base import BaseHandler
from django.http import HttpRequest
from django.http import HttpResponse
from django.http import parse_cookie
from django.http.request import HttpHeaders
from playwright.async_api import Request


class RequestHandlerResponseStatus(Enum):
    SUCCESS = "success"
    CONTINUE = "continue"
    ABORT = "abort"


class RequestHandlerResponse:
    def __init__(self, status: RequestHandlerResponseStatus, payload=None):
        self.status = status
        self.payload = payload

    def __str__(self):
        return str(self.payload)


class RequestHandler:
    """Base RequestHandler class

    A RequestHandler tells the renderer how to handle network requests that occur during the rendering process.
    """

    source_url: str | None = None
    request_meta: dict[str, str] | None = None
    debug: bool | None = None
    media_url: str | None = None
    media_root: str = ""
    static_url: str | None = None
    static_roots: list[tuple[str | None, str]] = []
    log = print  # noqa

    def setup(self, context, log):
        self.source_url = context["source_url"]
        self.request_meta = context["request_meta"]
        self.debug = settings.DEBUG
        self.media_url = str(settings.MEDIA_URL)
        self.media_root = str(settings.MEDIA_ROOT)
        self.static_url = str(settings.STATIC_URL)
        self.static_roots = get_static_roots()
        self.log = log

    def handle_request(self, request: Request) -> RequestHandlerResponse | None:
        """Handle request and return the response"""
        raise NotImplementedError

    def serialize(self):
        """Serialize handler data so can be reconstructed in a different process

        This always includes ``path`` which is used to identify the class to construct.

        ``deserialize`` is used to construct a new instance of the class from the serialized data.
        """
        module = self.__module__
        path_name = module + "." + self.__class__.__name__
        return {"path": path_name}

    @classmethod
    def deserialize(cls, data=None):
        """Construct an instance of this class from the serialized data"""
        data = data or {}
        return cls(**data)


class DjangoHTTPRequest(HttpRequest):
    def __init__(self, url, meta, method, headers, post_data):
        super().__init__()
        scheme, netloc, path, params, query, fragment = urlparse(url)
        self._scheme = scheme
        self.path = path
        self.path_info = path
        self.method = method
        self.content_type = headers.get("Content-Type")
        self._body = post_data

        self.META = dict(meta)
        for key, value in headers.items():
            self.META["HTTP_" + key.upper().replace("-", "_")] = value

        original_headers = HttpHeaders(meta)
        cookies = original_headers.get("cookie")
        if cookies:
            self.COOKIES.update(parse_cookie(cookies))

        for key, value in parse_qs(query).items():
            # QueryDicts are immutable during a Request/Response cycle, but not initially - we still can set it
            # in __init__ (`self.GET = QueryDict(mutable=True)`)
            self.GET.setlist(key, value)

    def _get_scheme(self):
        return self._scheme


class DjangoRequestHandler(RequestHandler):
    """
    Handle requests that should be processed by django.
    """

    def build_django_request(self, request: Request) -> HttpRequest:
        django_request = DjangoHTTPRequest(
            request.url,
            self.request_meta,
            request.method,
            request.headers,
            request.post_data,
        )
        return django_request

    def handle_request(self, request: Request) -> RequestHandlerResponse | None:
        request_url = urlparse(request.url)
        if urlparse(self.source_url).netloc == request_url.netloc:
            handler = BaseHandler()
            handler.load_middleware()
            response: HttpResponse = cast(
                HttpResponse, handler.get_response(self.build_django_request(request))
            )
            resp = {
                "status": response.status_code,
                "headers": dict(response.headers),
                "body": response.content,
            }
            return RequestHandlerResponse(RequestHandlerResponseStatus.SUCCESS, resp)
        return None


class StaticHttpRequestHandler(RequestHandler):
    """Handle static files.

    Any request that has a URL starting with the sites static URL will be handled.
    """

    def handle_request(self, request: Request) -> RequestHandlerResponse | None:
        if self.static_url is None:
            return None
        request_url = urlparse(request.url)
        source_url = urlparse(self.source_url)
        if source_url.netloc == request_url.netloc:
            if request_url.path.startswith(self.static_url):
                full_path = get_static_url(
                    self.static_roots, request_url.path[len(cast(str, self.static_url)) :]
                )
                if not full_path:
                    self.log(
                        "error",
                        "static file not found: %s, %s, %s"
                        % (
                            request_url.path,
                            self.static_roots,
                            request_url.path[len(cast(str, self.static_url)) :],
                        ),
                    )
                    return RequestHandlerResponse(RequestHandlerResponseStatus.ABORT)
                response = get_response_from_fullpath(full_path, request_url.path)
                return RequestHandlerResponse(RequestHandlerResponseStatus.SUCCESS, response)
        return None


class WhitelistDomainRequestHandler(RequestHandler):
    """Allow requests from the specified domains"""

    domains: list[str]

    def __init__(self, domains: list[str]):
        """

        Args:
            domains: List of domains that are allowed
        """
        self.domains = domains
        super().__init__()

    def serialize(self):
        return {**super().serialize(), "domains": self.domains}

    def handle_request(self, request: Request) -> RequestHandlerResponse | None:
        request_url = urlparse(request.url)
        parsed_locs = []
        for domain in self.domains:
            parsed_locs.append(urlparse(domain).netloc)
        if request_url.netloc in parsed_locs:
            return RequestHandlerResponse(RequestHandlerResponseStatus.CONTINUE)
        return None


class PassThroughRequestHandler(RequestHandler):
    """
    This handler will pass through all requests to be handled by the client.
    """

    def handle_request(self, request: Request) -> RequestHandlerResponse:
        return RequestHandlerResponse(RequestHandlerResponseStatus.CONTINUE)


class MediaHttpRequestHandler(RequestHandler):
    """Handle media files, both S3 buckets and local storage.

    Any request that has a URL starting with the sites medial URL will be handled
    """

    def handle_request(self, request: Request) -> RequestHandlerResponse | None:
        if self.media_url is None:
            return None
        request_url = urlparse(request.url)
        if urlparse(self.media_url).netloc and request.url.startswith(self.media_url):
            return RequestHandlerResponse(RequestHandlerResponseStatus.CONTINUE)
        if request_url.path.startswith(self.media_url):
            response = get_response_from_path(
                self.media_root, request_url.path[len(cast(str, self.media_url)) :]
            )
            return RequestHandlerResponse(RequestHandlerResponseStatus.SUCCESS, response)
        return None


class CustomRequestHandler(RequestHandler):
    """
    Handle requests to specific urls with custom html, e.g.

    .. code-block:: python

        CustomRequestHandler({
            'http://foo.com/bar/': {
                'body': '<html><body>Content</body></html>',
                'status': 201, (200 is the default)
                'headers': {
                    'X-Some-Header: 'foo',
                },
            }
        })

    Note that urls are normalized with regard to trailing slash, so if you set
    http://foo.com/bar/ as the url, it will match to http://foo.com/bar/ or http://foo.com/bar.
    However the full url (scheme, netloc, etc.) *is* required in order to match.
    """

    def __init__(self, routes):
        self.routes = {url.rstrip("/"): config for url, config in routes.items()}

    def serialize(self):
        data = super().serialize()
        data["routes"] = self.routes
        return data

    def handle_request(self, request: Request) -> RequestHandlerResponse | None:
        request_url = request.url.rstrip("/")
        if request_url in self.routes:
            payload = self.routes[request_url]
            if "headers" not in payload:
                payload["headers"] = {}
            if "status" not in payload:
                payload["status"] = 200
            return RequestHandlerResponse(RequestHandlerResponseStatus.SUCCESS, payload)
        return None
