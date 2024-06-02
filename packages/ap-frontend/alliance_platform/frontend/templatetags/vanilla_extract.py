from pathlib import Path
import warnings

from allianceutils.template import is_static_expression
from allianceutils.template import parse_tag_arguments
from django import template
from django.template import Context
from django.template import Origin
from django.template.base import UNKNOWN_SOURCE

from ..bundler import get_bundler
from ..bundler.base import ResolveContext
from ..bundler.context import BundlerAsset
from ..bundler.vanilla_extract import resolve_vanilla_extract_class_mapping

register = template.Library()


class VanillaExtractStylesheetNode(template.Node, BundlerAsset):
    def __init__(self, filename: Path, origin: Origin | None, attrs=None, css_modules_target_var=None):
        self.filename = filename
        self.attrs = attrs
        self.css_modules_target_var = css_modules_target_var
        super().__init__(origin or Origin(UNKNOWN_SOURCE))

    def get_paths_for_bundling(self) -> list[Path]:
        return [self.filename]

    def render(self, context: Context):
        if self.css_modules_target_var:
            context[self.css_modules_target_var] = resolve_vanilla_extract_class_mapping(
                self.bundler, self.filename
            )
        # TODO: Currently HMR works but it forces a full refresh of the page always. Not clear why.
        # One solution is to write out a temporary `.ts` file that loads the css file. This sort of worked
        # but was a bit flakey so I've removed it for the time being. Needs further investigation into
        # cause.
        items = self.bundler.get_embed_items(self.get_paths_for_bundling())
        for item in items:
            self.bundler_asset_context.queue_embed_file(item)
        # Nothing to render - tags are added to head
        return ""


@register.tag("stylesheet")
def stylesheet(parser: template.base.Parser, token: template.base.Token):
    """
    Add a vanilla extract CSS file the page, optionally exposing class name mapping in a template variable.

    If the CSS file includes exported class names, you can access the mapping by specifying a variable with the syntax
    ``as <var name>``. This functionality relies on the plugin defined by in ``vanillaExtractWithExtras.ts``.

    If you do not specify a variable using the ``as <var name>`` syntax, the styles will only be available globally,
    and any specified variables will be ignored.

    For more information on how paths are resolved, refer to the documentation on :ref:`resolving_paths`.

    The CSS file is not embedded inline where the tag is used, rather it is added by the :meth:`~alliance_platform.frontend.templatetags.bundler.bundler_embed`
    tag.

    Usage:

    .. code-block:: html+django

        {% load vanilla_extract %}

        {% stylesheet "./myView.css.ts" as styles %}

        <div class="{{ styles.section }}">
            <h1 class="{{ styles.heading }}">My View</h1>
            ...
        </div>


    .. note:: If you need to include a plain CSS file use the :meth:`~alliance_platform.frontend.templatetags.bundler.bundler_embed`
            tag instead.

    """
    tag_name = token.split_contents()[0]
    args, kwargs, target_var = parse_tag_arguments(parser, token, supports_as=True)

    if len(args) != 1:
        raise template.TemplateSyntaxError(
            f"'{tag_name}' must receive a single argument which is the name of the stylesheet to include"
        )

    if not is_static_expression(args[0]):
        raise template.TemplateSyntaxError(
            f"'{tag_name}' must be passed a static string for it's argument (encountered variable '{args[0].var}')"
        )
    f = args[0].resolve(Context())
    bundler = get_bundler()
    resolver_context = ResolveContext(bundler.root_dir, parser.origin.name if parser.origin else None)
    filename = bundler.resolve_path(
        f,
        resolver_context,
        suffix_whitelist=[".css.ts"],
        suffix_hint=f'This tag is for vanilla-extract .css.ts files only. To embed a regular stylesheet just use {{% bundler_embed "{f}" %}}',
    )
    return VanillaExtractStylesheetNode(filename, parser.origin, kwargs, css_modules_target_var=target_var)


@register.filter
def style_key(styles, key):
    if key not in styles:
        warnings.warn(f"Could not find style key '{key}'. Known keys: {', '.join(styles)}")
        return ""
    return styles[key]
