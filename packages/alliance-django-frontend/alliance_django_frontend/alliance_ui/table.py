from __future__ import annotations

from django import template
from django.template import Library

from .utils import get_module_import_source
from ..templatetags.react import parse_component_tag


def table(parser: template.base.Parser, token: template.base.Token):
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "Table", False, parser.origin),
    )


def table_header(parser: template.base.Parser, token: template.base.Token):
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "TableHeader", False, parser.origin),
    )


def table_body(parser: template.base.Parser, token: template.base.Token):
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "TableBody", False, parser.origin),
    )


def column_header_link(parser: template.base.Parser, token: template.base.Token):
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source(
            "@alliancesoftware/ui", "ColumnHeaderLink", False, parser.origin
        ),
    )


def row(parser: template.base.Parser, token: template.base.Token):
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "Row", False, parser.origin),
    )


def column(parser: template.base.Parser, token: template.base.Token):
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "Column", False, parser.origin),
    )


def cell(parser: template.base.Parser, token: template.base.Token):
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "Cell", False, parser.origin),
    )


def register_table(register: Library):
    register.tag("Table")(table)
    register.tag("TableHeader")(table_header)
    register.tag("TableBody")(table_body)
    register.tag("ColumnHeaderLink")(column_header_link)
    register.tag("Column")(column)
    register.tag("Row")(row)
    register.tag("Cell")(cell)
