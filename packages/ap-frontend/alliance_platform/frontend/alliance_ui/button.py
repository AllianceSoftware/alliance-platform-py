from django import template
from django.template import Library

from ..templatetags.react import parse_component_tag
from .utils import get_module_import_source


def button(parser: template.base.Parser, token: template.base.Token):
    """
    Render a ``Button`` component from the Alliance UI React library with the specified props.

    If used for a link, the :function:`~alliance_platform.templatetags.alliance_ui.url_with_perms_filter`
    or :function:`~alliance_platform.frontend.templatetags.alliance_ui.url_filter` can be used to handle
    url args, or hide if the link is not available.
    """
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "Button", False, parser.origin),
    )


def button_group(parser: template.base.Parser, token: template.base.Token):
    """Render a ``ButtonGroup`` component from the Alliance UI React library with the specified props."""
    return parse_component_tag(
        parser,
        token,
        asset_source=get_module_import_source("@alliancesoftware/ui", "ButtonGroup", False, parser.origin),
    )


def register_button(register: Library):
    register.tag("Button")(button)
    register.tag("ButtonGroup")(button_group)
