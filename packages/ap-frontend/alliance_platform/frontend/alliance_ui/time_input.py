from django import template
from django.template import Context
from django.template import Library
from django.utils.dateparse import parse_time

from ..templatetags.react import ComponentNode
from ..templatetags.react import ComponentProps
from ..templatetags.react import parse_component_tag
from .utils import get_module_import_source


class TimeInputNode(ComponentNode):
    def resolve_props(self, context: Context) -> ComponentProps:
        values = super().resolve_props(context)
        if values.has_prop("defaultValue") and isinstance(values.props["defaultValue"], str):
            values.update(
                {"defaultValue": self.resolve_prop(parse_time(values.props["defaultValue"]), context)}
            )
        return values


def time_input(parser: template.base.Parser, token: template.base.Token):
    """Render a ``TimeInput`` component from the Alliance UI library. with the specified props"""
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "TimeInput", False, parser.origin),
        node_class=TimeInputNode,
    )


def register_time_input(register: Library):
    register.tag("TimeInput")(time_input)
