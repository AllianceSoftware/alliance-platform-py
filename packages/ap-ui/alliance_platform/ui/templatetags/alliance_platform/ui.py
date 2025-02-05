from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from allianceutils.auth.permission import reverse_if_probably_allowed
from allianceutils.template import parse_tag_arguments
from django import template
from django.db.models import Model
from django.http import HttpRequest
from django.http import QueryDict
from django.template import Context
from django.urls import reverse

from alliance_platform.frontend.templatetags.react import DeferredProp
from alliance_platform.frontend.templatetags.react import OmitComponentFromRendering

from .button import register_button
from .date_picker import register_date_picker
from .icon import register_icon
from .inline_alert import register_inline_alert
from .labeled_input import register_labeled_input
from .menubar import register_menubar
from .misc import register_misc
from .pagination import register_pagination
from .table import register_table
from .time_input import register_time_input

register = template.Library()

register_menubar(register)
register_table(register)
register_pagination(register)
register_button(register)
register_misc(register)
register_inline_alert(register)
register_icon(register)
register_date_picker(register)
register_time_input(register)
register_labeled_input(register)

QueryParams = dict[str, Any] | QueryDict | str


class NamedUrlDeferredProp(DeferredProp):
    """Used by ``url_with_perm`` and ``url`` filters to defer the resolution of a URL until rendering time.

    This allows perm checks to occur and to omit the component from rendering if failed
    """

    url_name: str
    check_perm: bool
    args: list[Any]
    kwargs: dict[str, Any]
    params: str
    object: Model | None

    def __init__(self, url_name, check_perm=False):
        self.url_name = url_name
        self.check_perm = check_perm
        self.args = []
        self.kwargs = {}
        self.query_string = ""
        self.object = None
        super().__init__()

    def set_object(self, arg: Model):
        self.object = arg

    def add_arg(self, arg: Any):
        self.args.append(arg)

    def add_kwargs(self, kwargs: dict[str, Any]):
        self.kwargs.update(kwargs)

    def add_params(self, params: QueryParams):
        if not params:
            return

        if isinstance(params, str):
            query_string = params
        elif isinstance(params, QueryDict):
            query_string = params.urlencode()
        else:
            query_string = urlencode(params)

        # query string will be blank if no params have been added
        if not self.query_string:
            self.query_string = "?"
        elif query_string and not query_string.startswith("&") and not self.query_string.endswith("&"):
            self.query_string += "&"

        self.query_string += query_string

    def resolve(self, context: Context):
        if self.check_perm:
            url = reverse_if_probably_allowed(
                context["request"],
                self.url_name,
                object=self.object,
                args=self.args,
                kwargs=self.kwargs,
            )
            if url is None:
                raise OmitComponentFromRendering()
        else:
            url = reverse(self.url_name, args=self.args, kwargs=self.kwargs)

        if self.query_string:
            url += self.query_string

        return url


class QueryParamsNode(template.Node):
    def __init__(
        self,
        params: dict[str, Any],
        target_var=None,
    ):
        if not target_var:
            raise template.TemplateSyntaxError("Specify variable name for query params to be passed as")
        self.params = params
        self.target_var = target_var

    def render(self, context):
        params = {key: value.resolve(context) for key, value in self.params.items()}
        context[self.target_var] = params
        return ""


@register.tag("query_params")
def query_params(parser: template.base.Parser, token: template.base.Token):
    """Pass arbitrary keyword arguments to generate a dictionary with the corresponding keys.

    Needs to be assigned a target var with ``{% query_params as variable %}`` to be
    passed to a url.
    """
    _, kwargs, target_var = parse_tag_arguments(
        parser,
        token,
        supports_as=True,
    )

    return QueryParamsNode(params=kwargs, target_var=target_var)


@register.filter("url_with_perm")
def url_with_perm_filter(value, arg1=None):
    """Resolve a URL and check if the current user has permission to access it.

    If permission check fails, the component that uses the value will be omitted from rendering.
    """
    pfv = NamedUrlDeferredProp(value, True)
    if arg1 is not None:
        pfv.add_arg(arg1)
    return pfv


@register.filter("url")
def url_filter(value, arg1=None):
    """Behaves same as ``url_with_perm`` but does not check any permissions."""
    pfv = NamedUrlDeferredProp(value)
    if arg1 is not None:
        pfv.add_arg(arg1)
    return pfv


@register.filter("with_arg")
def with_arg(value: NamedUrlDeferredProp, arg):
    """Add an argument to a ``url_with_perm`` or ``url`` filter."""
    value.add_arg(arg)
    return value


@register.filter("with_kwargs")
def with_kwargs(value: NamedUrlDeferredProp, kwargs):
    """Add kwargs to a ``url_with_perm`` or ``url`` filter."""
    value.add_kwargs(kwargs)
    return value


@register.filter("with_params")
def with_params(value: NamedUrlDeferredProp, kwargs):
    """Add query parameters to a ``url_with_perm`` or ``url`` filter. Accepts a string, dict, or QueryDict."""
    value.add_params(kwargs)
    return value


@register.filter("with_perm_obj")
def with_perm_object(value: NamedUrlDeferredProp, arg):
    """Add an object to a ``url_with_perm`` filter for the purposes of object level permission checks."""
    if not isinstance(value, NamedUrlDeferredProp):
        raise ValueError(
            '`perm_obj` must appear after `url_with_perm`, eg. `"url_name"|url_with_perm:obj.pk|with_perm_obj:obj'
        )
    value.set_object(arg)
    return value


@register.filter("unwrap_list")
def unwrap_list(value):
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        if len(value) != 1:
            raise ValueError(f"Expected list of length 1, received length {len(value)}: {value}")
        return value[0]
    return value


@register.filter
def table_sort_order(request: HttpRequest, ordering_param: str = "ordering"):
    """Extract the current sort ordering from the request GET parameters and return it as a list of dicts

    Each ordering entry is a dict with keys "column" and "direction".

    For example, the URL /foo?ordering=-bar,email would return::

        [
          {'column': 'email', 'direction': 'ascending'},
          {'column': 'name', 'direction': 'descending'}
        ]
    """
    query = request.GET.copy()
    current_sorting_str = query.get(ordering_param)
    if current_sorting_str:
        return [
            {
                "column": x[1:] if x.startswith("-") else x,
                "direction": "descending" if x.startswith("-") else "ascending",
            }
            for x in current_sorting_str.split(",")
        ]
    return []
