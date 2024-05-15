from __future__ import annotations

from django import template
from django.template import Library

from ..templatetags.react import parse_component_tag
from .utils import get_module_import_source


def menubar(parser: template.base.Parser, token: template.base.Token):
    """Render a ``Menubar`` component from the Alliance UI library with the specified props"""
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "Menubar", False, parser.origin),
    )


def submenu(parser: template.base.Parser, token: template.base.Token):
    """Render a ``Menubar.SubMenu`` component from the Alliance UI library with the specified props"""
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source(
            "@alliancesoftware/ui", "Menubar", False, parser.origin, property_name="SubMenu"
        ),
    )


def menubar_item(parser: template.base.Parser, token: template.base.Token):
    """
    Render a ``Menubar.Item`` component from the Alliance UI library with the specified props

    If used for a link, the :function:`~alliance_platform.frontend.templatetags.alliance_ui.url_with_perms_filter``
    or :function:`~alliance_platform.templatetags.alliance_ui.url_filter`` can be used to handle
    url args, or hide if the link is not available.
    """
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "Item", False, parser.origin),
    )


def menubar_section(parser: template.base.Parser, token: template.base.Token):
    """Render a ``Menubar.Section`` component from the Alliance UI library with the specified props"""
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
