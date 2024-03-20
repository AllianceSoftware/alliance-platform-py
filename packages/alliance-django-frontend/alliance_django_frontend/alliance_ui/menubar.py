from __future__ import annotations

from django import template
from django.template import Library

from common_frontend.alliance_ui.utils import get_module_import_source
from common_frontend.templatetags.react import parse_component_tag


def menubar(parser: template.base.Parser, token: template.base.Token):
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "Menubar", False, parser.origin),
    )


def submenu(parser: template.base.Parser, token: template.base.Token):
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source(
            "@alliancesoftware/ui", "Menubar", False, parser.origin, property_name="SubMenu"
        ),
    )


def menubar_item(parser: template.base.Parser, token: template.base.Token):
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "Item", False, parser.origin),
    )


def menubar_section(parser: template.base.Parser, token: template.base.Token):
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "Section", False, parser.origin),
    )


def register_menubar(register: Library):
    register.tag("Menubar")(menubar)
    register.tag("Menubar.SubMenu")(submenu)
    register.tag("Menubar.Item")(menubar_item)
    register.tag("Menubar.Section")(menubar_section)
