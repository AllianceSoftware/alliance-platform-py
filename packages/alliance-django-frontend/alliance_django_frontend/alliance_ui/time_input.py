from django import template
from django.template import Context
from django.template import Library
from django.utils.dateparse import parse_time

from common_frontend.alliance_ui.utils import get_module_import_source
from common_frontend.templatetags.react import ComponentNode
from common_frontend.templatetags.react import ComponentProps
from common_frontend.templatetags.react import parse_component_tag


class TimeInputNode(ComponentNode):
    def resolve_props(self, context: Context) -> ComponentProps:
        values = super().resolve_props(context)
        if values.has_prop("default_value") and isinstance(values.props["default_value"], str):
            values.update(
                {"default_value": self.resolve_prop(parse_time(values.props["default_value"]), context)}
            )
        return values


def time_input(parser: template.base.Parser, token: template.base.Token):
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "TimeInput", False, parser.origin),
        node_class=TimeInputNode,
    )


def register_time_input(register: Library):
    register.tag("TimeInput")(time_input)
