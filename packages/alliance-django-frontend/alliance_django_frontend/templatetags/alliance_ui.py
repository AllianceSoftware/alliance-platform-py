from __future__ import annotations

from typing import Any

from django import template
from django.db.models import Model
from django.template import Context
from django.urls import reverse

from ..alliance_ui.button import register_button
from ..alliance_ui.date_picker import register_date_picker
from ..alliance_ui.icon import register_icon
from ..alliance_ui.inline_alert import register_inline_alert
from ..alliance_ui.menubar import register_menubar
from ..alliance_ui.misc import register_misc
from ..alliance_ui.pagination import register_pagination
from ..alliance_ui.table import register_table
from ..alliance_ui.time_input import register_time_input
from .react import DeferredProp
from .react import OmitComponentFromRendering
from allianceutils.auth.permission import reverse_if_probably_allowed

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


class NamedUrlDeferredProp(DeferredProp):
    """Used by ``url_with_perm`` and ``url`` filters to defer the resolution of a URL until rendering time.

    This allows perm checks to occur and to omit the component from rendering if failed"""

    url_name: str
    check_perm: bool
    args: list[Any]
    kwargs: dict[str, Any]
    object: Model | None

    def __init__(self, url_name, check_perm=False):
        self.url_name = url_name
        self.check_perm = check_perm
        self.args = []
        self.kwargs = {}
        self.object = None
        super().__init__()

    def set_object(self, arg: Model):
        self.object = arg

    def add_arg(self, arg: Any):
        self.args.append(arg)

    def add_kwargs(self, kwargs: dict[str, Any]):
        self.kwargs.update(kwargs)

    def resolve(self, context: Context):
        if self.check_perm:
            url = reverse_if_probably_allowed(
                context["request"], self.url_name, object=self.object, args=self.args, kwargs=self.kwargs
            )
            if url is None:
                raise OmitComponentFromRendering()
            return url
        return reverse(self.url_name, args=self.args, kwargs=self.kwargs)


@register.filter("url_with_perm")
def url_with_perm_filter(value, arg1=None):
    """Resolve a URL and check if the current user has permission to access it.

    If permission check fails, the component that uses the value will be omitted from rendering.

    Usage::

        {% component "a" href="my_url_name"|url_with_perm:2 %}

    The above example will resolve the URL "my_url_name" with the argument ``2``.

    If you need multiple arguments you can use the ``with_arg`` filter::


        {% component "a" href="my_url_name"|url_with_perm:2|with_arg:"another arg" %}

    To pass kwargs you can use the ``with_kwargs`` filter::

        {% component "a" href="my_url_name"|url_with_perm|with_kwargs:my_kwargs %}

    Note that as there's no way to define a dictionary in the standard Django template language, you'll need to
    pass it in context.

    To do object level permission checks use the ``with_perm_obj`` filter to pass through the object::

        {% component "a" href="my_url_name"|url_with_perm:obj.pk|with_obj:obj %}

    Note that you still have to pass through the pk to resolve the URL with. Passing the object just allows the permission
    checks to work without having to manually look up the object. Due to how the ``DetailView.get_object`` method works,
    if you are not going to pass the object you must use ``with_kwargs`` to pass through the ID rather than a positional
    argument::

        {% component "a" href="my_url_name"|url_with_perm|with_kwargs:kwargs %}

    Note that the above would do a query to retrieve the object, so it's better to pass the object if you have already
    retrieved it.
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
