from functools import wraps
from typing import Callable

from alliance_platform.core.util import strtobool
from alliance_platform.pdf.render import render_pdf
from django.http import HttpRequest
from django.http import HttpResponse

QueryParamPredicate = Callable[[HttpRequest], bool]

try:
    from alliance_platform.frontend.bundler.context import BundlerAssetContext

    AP_FRONTEND_INSTALLED = True
except ImportError:
    AP_FRONTEND_INSTALLED = False


def view_as_pdf(
    optional: bool = True,
    query_param_test: str | QueryParamPredicate = "pdf",
    request_headers: dict[str, str] | None = None,
    extra_headers: dict[str, str | None] | None = None,
    url_path: str | None = None,
    **render_options,
):
    """
    Decorator that can wrap a django view, and return the view html as a PDF if a
    given URL parameter is present in the request. E.g.

    .. code-block:: python

        @view_as_pdf(pass_through=True):
        def my_view(request):
            return HttpResponse('Some content')

    This will return the normal view response unless :code:`pdf=<something truthy>` is present
    in the query parameters, in which case it will return the same content rendered as a PDF.

    Args:

        optional: If not True then will always render as PDF otherwise will only render as
            PDF if :code:`query_param_test` check passes.
        query_param_test: If a string is passed, it will be interpreted as a query parameter,
            and if that query parameter is present and truthy (using strtobool) the view will be rendered
            as a PDF. If more control is needed, you can pass a function here that takes the request as
            an argument and returns a bool to indicate whether to render as PDF (if the predicate returns True) or
            return the normal view response (if the predicate returns False).
        request_headers: The complete set of headers to pass through on network requests triggered
            by pdf rendering (if you just want to add/override certain request headers, use extra_headers instead).
            If you set this to an empty dictionary, this implies that NO headers will be sent.
        extra_headers: Additional headers that will override/add to the existing request headers on network
            requests triggered by pdf rendering. Any header set to None here will be removed from the request.
        url_path: Optional path to override the request url path. This can be useful when rendering
            a view that returns a single page app, and you want to control the route that is seen by the SPA.
            E.g.

            .. code-block:: python

                view_as_pdf(optional=False, location='/admin/users/')(
                    django_site.views.FrontendView.as_view(
                        site=admin_site,
                        basename='admin',
                        entry_point='admin',
                    )
                )

            Will render the frontend template for admin site, and the SPA will see the route as /admin/users/
            and render that page accordingly.

        **render_options: The remaining options are passed through to :meth:`~alliance_platform.pdf.render.render_pdf`

    """

    if not isinstance(query_param_test, str) and not callable(query_param_test):
        raise TypeError("Argument query_param_test should be a string or a function")

    def decorator(func):
        @wraps(func)
        def inner(request, *args, **kwargs):
            if not optional:
                render_as_pdf = True
            else:
                if isinstance(query_param_test, str):
                    render_as_pdf = bool(
                        strtobool(request.GET.get(query_param_test, "0"))
                    )  # who knows - strtobool returns int not bool.
                else:
                    render_as_pdf = query_param_test(request)

            if render_as_pdf:
                headers = extract_request_headers(request) if request_headers is None else request_headers
                if extra_headers:
                    for key, val in extra_headers.items():
                        if val is None:
                            headers.pop(key, None)
                            request.META.pop(key, None)
                        else:
                            headers[key] = val
                            request.META[key] = val

            if AP_FRONTEND_INSTALLED:
                with BundlerAssetContext(request=request) as asset_context:
                    response = func(request, *args, **kwargs)
                    if hasattr(response, "render") and callable(response.render):
                        response = response.render()

                    if asset_context.requires_post_processing():
                        response.content = asset_context.post_process(response.content.decode()).encode()
            else:
                response = func(request, *args, **kwargs)
                if hasattr(response, "render") and callable(response.render):
                    response = response.render()

            if render_as_pdf:
                url = request.build_absolute_uri(request.path if not url_path else url_path)
                return render_pdf_response(
                    url=url,
                    html=response.content.decode("utf-8"),
                    request_headers=headers,
                    **render_options,
                )

            return response

        return inner

    return decorator


def extract_request_headers(request: HttpRequest):
    return {key: val for key, val in request.META.items() if isinstance(val, str)}


def render_pdf_response(**render_options):
    pdf_data = render_pdf(**render_options)
    return HttpResponse(content=pdf_data, content_type="application/pdf")
