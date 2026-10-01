"""Diagnostics reported by static ``{% ui %}`` components.

Renderers report problems with :func:`report`, or ``self.report()`` on
:class:`~alliance_platform.ui.html_components.base.BaseHtmlUIComponentRenderer`, rather than through
Python's ``warnings`` module. Each report has a kind:

``contract``
    A problem fixed in template source or the environment: an unsupported or invalid prop, a missing
    required prop, a component outside its required parent, a missing icon file or style variable.
``data``
    A value that can legitimately vary per request, such as a page number past the last page.

Reports log at ``WARNING`` through the ``alliance_platform.ui`` logger. The log message is the report's
text exactly; the record also carries ``component``, ``origin`` (the template name) and ``kind``
attributes. Outside ``DEBUG`` a contract report logs once per process for each component and message,
while data reports always log. When the ``STATIC_COMPONENT_STRICT`` UI setting is on, which it is by
default when ``DEBUG`` is on, a contract report raises :class:`StaticComponentContractError` instead of
logging.
"""

from __future__ import annotations

import logging
from typing import Literal

from django.conf import settings
from django.template import Origin
from django.template.base import UNKNOWN_SOURCE

from ..settings import ap_ui_settings

#: The logger diagnostics are logged through
LOGGER_NAME = "alliance_platform.ui"

logger = logging.getLogger(LOGGER_NAME)

DiagnosticKind = Literal["contract", "data"]

# (component, message) keys of the contract reports logged so far in this process. Messages can embed
# runtime values, so the set is cleared when it fills up rather than growing without limit.
_MAX_REMEMBERED_REPORTS = 1024
_reported: set[tuple[str | None, str]] = set()


class StaticComponentContractError(Exception):
    """Raised for a ``contract`` report while the ``STATIC_COMPONENT_STRICT`` setting is on.

    The message is the report's text followed by the component and template when they are known, for
    example ``"Prop 'onPress' will be ignored: ... (component 'button' in nav.html)"``.
    """

    #: Name of the component that made the report, or ``None`` if unknown
    component: str | None
    #: Template origin of the tag that made the report, or ``None`` if unknown
    origin: Origin | None

    def __init__(self, message: str, *, component: str | None = None, origin: Origin | None = None):
        super().__init__(_describe_location(message, component, origin))
        self.component = component
        self.origin = origin


def report(
    message: str,
    *,
    kind: DiagnosticKind,
    component: str | None = None,
    origin: Origin | None = None,
) -> None:
    """Report a problem found while rendering a static component.

    Args:
        message: What is wrong. It is logged exactly as given.
        kind: ``"contract"`` for a problem fixed in template source or the environment, ``"data"`` for a
            value that can legitimately vary per request.
        component: Name of the component making the report.
        origin: Template origin of the tag making the report.

    Raises:
        StaticComponentContractError: For a ``contract`` report while ``STATIC_COMPONENT_STRICT`` is on.
    """
    if kind not in ("contract", "data"):
        raise ValueError(f"Unknown diagnostic kind {kind!r}; use 'contract' or 'data'")
    if origin is not None and origin.name == UNKNOWN_SOURCE:
        origin = None
    if kind == "contract":
        if ap_ui_settings.STATIC_COMPONENT_STRICT:
            raise StaticComponentContractError(message, component=component, origin=origin)
        if not settings.DEBUG and _already_reported((component, message)):
            return
    logger.warning(
        message,
        extra={
            "component": component,
            "origin": origin.name if origin is not None else None,
            "kind": kind,
        },
    )


def _already_reported(key: tuple[str | None, str]) -> bool:
    if key in _reported:
        return True
    if len(_reported) >= _MAX_REMEMBERED_REPORTS:
        _reported.clear()
    _reported.add(key)
    return False


def _reset_reported():
    """Forget which contract reports were logged, so the next of each logs again."""
    _reported.clear()


def _describe_location(message: str, component: str | None, origin: Origin | None) -> str:
    location = []
    if component:
        location.append(f"component '{component}'")
    if origin is not None:
        location.append(f"in {origin.name}")
    if not location:
        return message
    return f"{message} ({' '.join(location)})"
