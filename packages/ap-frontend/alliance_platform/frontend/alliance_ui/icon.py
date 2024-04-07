from allianceutils.template import is_static_expression
from django import template
from django.template import Context
from django.template import Library
from django.template import TemplateSyntaxError
from django.template.base import Token

from ..bundler import get_bundler
from ..bundler.base import ResolveContext
from ..templatetags.react import ImportComponentSource
from ..templatetags.react import parse_component_tag


def icon(parser: template.base.Parser, token: template.base.Token):
    """Render an icon from the core-ui/icons directory

    This tag accepts no children, so it requires no `endIcon`.

    Pass the name of the icon to the tag, and then any props you want to pass to the icon component.

    Usage::

       {% Icon "Pencil" data-testid="pencil" %}
    """
    contents = token.split_contents()
    icon_name_filter = parser.compile_filter(contents.pop(1))
    context = Context()
    if not is_static_expression(icon_name_filter):
        raise TemplateSyntaxError(
            f"Icon must be passed a static string for the icon name, got {icon_name_filter}"
        )

    icon_name = icon_name_filter.resolve(context)
    token = Token(token.token_type, " ".join(contents))
    bundler = get_bundler()
    origin = parser.origin
    resolver_context = ResolveContext(bundler.root_dir, origin.name if origin else None)
    # This was previous approach to avoid cascading requests for every icon included in the barrel file. This approach
    # proves to be unnecessary when using the Vite metadata to extract optimised deps - see ViteBundler.get_vite_dev_metadata
    # and it's usage in that file. The optimised file doesn't cause the cascade of requests.
    # sub_dir = "outlined"
    # if icon_name.endswith("Solid"):
    #     sub_dir = "solid"
    # elif icon_name.endswith("DuoTone"):
    #     sub_dir = "duotone"
    # elif icon_name.endswith("DuoColor"):
    #     sub_dir = "duocolor"
    # source_path = get_bundler().resolve_path(
    #     f"@alliancesoftware/icons/{sub_dir}/{icon_name}",
    #     resolver_context,
    #     resolve_extensions=[".ts", ".tsx", ".js"],
    # )
    source_path = get_bundler().resolve_path(
        "@alliancesoftware/icons",
        resolver_context,
        resolve_extensions=[".ts", ".tsx", ".js"],
    )
    asset_source = ImportComponentSource(source_path, icon_name, False)
    return parse_component_tag(parser, token, asset_source=asset_source, no_end_tag=True)


def register_icon(register: Library):
    register.tag("Icon")(icon)
