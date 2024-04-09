from django import template
from django.template import Library

from ..templatetags.react import parse_component_tag
from .utils import get_module_import_source


def button(parser: template.base.Parser, token: template.base.Token):
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "Button", False, parser.origin),
    )


def button_group(parser: template.base.Parser, token: template.base.Token):
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "ButtonGroup", False, parser.origin),
    )


def register_button(register: Library):
    register.tag("Button")(button)
    register.tag("ButtonGroup")(button_group)
