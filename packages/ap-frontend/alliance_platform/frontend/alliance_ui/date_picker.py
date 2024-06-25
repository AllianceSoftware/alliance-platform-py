import warnings

from django import template
from django.template import Context
from django.template import Library
from django.utils.dateparse import parse_date
from django.utils.dateparse import parse_datetime

from ..templatetags.react import ComponentNode
from ..templatetags.react import ComponentProps
from ..templatetags.react import parse_component_tag
from .utils import get_module_import_source


class DatePickerNode(ComponentNode):
    def resolve_props(self, context: Context) -> ComponentProps:
        values = super().resolve_props(context)
        granularity = values.props.get("granularity", "day")
        if granularity not in {"day", "hour", "minute", "second"}:
            warnings.warn(
                f"Invalid granularity '{granularity}' passed to DatePicker. Defaulting to 'day'. If this is a datetime picker this will break."
            )
            granularity = "day"
            values.update({"granularity": self.resolve_prop(granularity, context)})

        if values.has_prop("defaultValue") and isinstance(values.props["defaultValue"], str):
            values.update(
                {
                    "defaultValue": self.resolve_prop(
                        (parse_date if granularity == "day" else parse_datetime)(
                            values.props["defaultValue"]
                        ),
                        context,
                    )
                }
            )
        return values


def date_picker(parser: template.base.Parser, token: template.base.Token):
    """Render a ``DatePicker`` component from the Alliance UI React library with the specified props."""
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "DatePicker", False, parser.origin),
        node_class=DatePickerNode,
    )


def register_date_picker(register: Library):
    register.tag("DatePicker")(date_picker)
