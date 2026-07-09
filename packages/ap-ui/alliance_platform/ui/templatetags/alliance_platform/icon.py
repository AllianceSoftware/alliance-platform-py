from allianceutils.template import is_static_expression
from allianceutils.template import parse_tag_arguments
from django import template
from django.template import Context
from django.template import Library
from django.template import TemplateSyntaxError
from django.template.base import NodeList
from django.template.base import Token

from alliance_platform.frontend.bundler import get_bundler
from alliance_platform.frontend.bundler.base import ResolveContext
from alliance_platform.frontend.templatetags.react import ImportComponentSource
from alliance_platform.frontend.templatetags.react import parse_component_tag
from alliance_platform.ui.icons import resolve_icon_style_dir
from alliance_platform.ui.templatetags.alliance_platform.html_components.components.icon import UIIconRenderer


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
    # Avoid imports from barrel file which causes worse performance in dev. Import direct
    # icon file instead.
    sub_dir = resolve_icon_style_dir(icon_name)
    source_path = get_bundler().resolve_path(
        f"@alliancesoftware/icons/{sub_dir}/{icon_name}",
        resolver_context,
        resolve_extensions=[".ts", ".tsx", ".js"],
    )
    asset_source = ImportComponentSource(source_path, icon_name, True)
    return parse_component_tag(parser, token, asset_source=asset_source, no_end_tag=True)


def static_icon(parser: template.base.Parser, token: template.base.Token):
    tag_name = token.split_contents()[0]
    args, kwargs, target_var = parse_tag_arguments(parser, token, supports_as=True)
    if len(args) == 0:
        raise TemplateSyntaxError(f"'{tag_name}' requires an icon name as the first positional argument")
    if len(args) > 1:
        raise TemplateSyntaxError(
            f"'{tag_name}' accepts exactly one positional argument (icon name), received {len(args)}"
        )
    if not is_static_expression(args[0]):
        raise TemplateSyntaxError(f"'{tag_name}' requires the icon name to be a static string literal")
    kwargs["name"] = args[0]
    return UIIconRenderer(
        props=kwargs,
        nodelist=NodeList(),
        origin=parser.origin,
        target_var=target_var,
    )


def register_icon(register: Library):
    register.tag("Icon")(icon)
    register.tag("icon")(static_icon)
