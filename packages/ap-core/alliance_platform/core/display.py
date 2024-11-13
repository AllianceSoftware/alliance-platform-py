import datetime
import decimal
from typing import Any

from django.utils import formats
from django.utils import timezone


def default_display_for_value(value: Any, empty_value_display: str | None = ""):
    """Return a string representation of a value for display to user

    Based on :meth:`django.contrib.admin.utils.display_for_value`

    Any project specific customisations should be added to :meth:`xenopus_frog_app.display.display_for_value`
    so that it's easier to pull in upstream changes.

    Args:
        value: The value to generate representation for
        empty_value_display: If ``value`` is ``None`` this will be returned instead
    """
    if value is None:
        return empty_value_display
    if isinstance(value, datetime.datetime):
        t = timezone.template_localtime(value)  # type: ignore[attr-defined] # template_localtime not in django-stubs
        return formats.localize(t)
    if isinstance(value, (datetime.date, datetime.time)):
        return formats.localize(value)
    # `bool` inherits from `int` so handle it before number_format below
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, decimal.Decimal, float)):
        return formats.number_format(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value)
    return str(value)
