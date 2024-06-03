from pathlib import Path
import warnings

from allianceutils.template import is_static_expression
from allianceutils.template import parse_tag_arguments
from allianceutils.template import resolve
from django import template
from django.template import Context
from django.template import Origin
from django.template.base import UNKNOWN_SOURCE
from django.template.base import FilterExpression
from django.template.loader import get_template
from django.utils.safestring import mark_safe

from ..bundler import get_bundler
from ..bundler.base import ResolveContext
from ..bundler.base import html_target_browser
from ..bundler.context import BundlerAsset
from ..bundler.context import BundlerAssetContext
from ..settings import ap_frontend_settings

register = template.Library()


class BundlerUrlAssetNode(template.Node, BundlerAsset):
    """
    The node used for the ``bundler_url`` tag.
    """

    def __init__(self, path: Path, origin: Origin | None, target_var: str | None = None):
        super().__init__(origin or Origin(UNKNOWN_SOURCE))
        self.path = path
        self.target_var = target_var

    def get_paths_for_bundling(self):
        return [self.path]

    def render(self, context):
        url = self.bundler.get_url(self.path)
        if self.target_var:
            context[self.target_var] = url
            return ""
        return url


class BundlerEmbedAssetNode(template.Node, BundlerAsset):
    """
    The node used for the ``bundler_embed`` tag
    """

    def __init__(
        self,
        path: Path,
        origin: Origin | None,
        target_var: str | None = None,
        inline=False,
        content_type: str | None = None,
        html_attrs: dict[str, str] | None = None,
    ):
        self.path = path
        self.target_var = target_var
        self.inline = inline
        self.html_attrs = html_attrs or {}
        self.content_type = content_type

        super().__init__(origin or Origin(UNKNOWN_SOURCE))

    def get_paths_for_bundling(self):
        return [self.path]

    def render(self, context):
        items = self.bundler.get_embed_items(self.get_paths_for_bundling(), self.content_type)
        tags = []
        for item in items:
            item.html_attrs = resolve(self.html_attrs, context)
            if not self.inline and not self.target_var and item.can_embed_head():
                self.bundler_asset_context.queue_embed_file(item)
            else:
                tags.append(item.generate_code(html_target_browser))
        code = mark_safe("\n".join(tags))
        if self.target_var:
            context[self.target_var] = code
            return ""
        return code


@register.tag("bundler_url")
def bundler_url(parser: template.base.Parser, token: template.base.Token):
    """
    Return the URL from the bundler to a specified asset.

    NOTE: This tag only accepts static values as :class:`extract_frontend_assets <alliance_platform.frontend.management.commands.extract_frontend_assets.Command>` needs to be able to statically generate
    a list of paths that need to be built for production.

    Usage::

        {% load bundler %}

        {% bundler_url "view.css" %}
    """
    tag_name = token.split_contents()[0]
    args, kwargs, target_var = parse_tag_arguments(parser, token, supports_as=True)

    if len(args) != 1:
        raise template.TemplateSyntaxError(
            f"{tag_name} must receive a single argument which is the path to the file to include"
        )

    if not is_static_expression(args[0]):
        raise template.TemplateSyntaxError(
            f"{tag_name} must be passed a static string for it's argument (encountered variable '{args[0].var}')"
        )
    bundler = get_bundler()
    resolver_context = ResolveContext(bundler.root_dir, parser.origin.name if parser.origin else None)
    filename = bundler.resolve_path(args[0].resolve(Context()), resolver_context)

    return BundlerUrlAssetNode(filename, parser.origin, target_var=target_var)


@register.simple_tag()
def bundler_preamble():
    """Adds necessary code for things like enabling HMR.

    Typically this is only required in development but that is up to the Bundler to decide - the tag should
    be included for both production and development.

    Usage::

        {% load bundler %}

        // In the <head> element
        {% bundler_preamble %}
    """
    return mark_safe(get_bundler().get_preamble_html())


@register.tag("bundler_embed")
def bundler_embed(parser: template.base.Parser, token: template.base.Token):
    """
    Return the embed HTML codes from the bundler to a specified asset.

    Each asset can have multiple files associated with it. For example, a component might have javascript and css. You
    can control which types of tags are included using the ``content_type`` kwarg. Common types are ``text/css`` and ``text/javascript``,
    but it is ultimately based on the file extension (e.g. ``.png`` will be ``image/png``). Note that ``.css.ts`` is handled
    as ``text/css`` and ``.ts`` and ``.tsx`` are handled as ``text/javascript``.

    By default, the tags are added to the HTML by the :meth:`~alliance_platform.frontend.templatetags.bundler.bundler_embed_collected_assets`.
    This allows assets to be embedded as needed in templates but all added in one place in the HTML (most likely the ``<head>``).
    You can force the tags to be outputted inline with ``inline=True``.
    """
    tag_name = token.split_contents()[0]
    args, kwargs, target_var = parse_tag_arguments(parser, token, supports_as=True)
    if len(args) != 1:
        raise template.TemplateSyntaxError(
            f"{tag_name} must receive a single argument which is the path to the file to include"
        )

    if not is_static_expression(args[0]):
        raise template.TemplateSyntaxError(
            f"{tag_name} must be passed a static string for it's argument (encountered variable '{args[0].var}')"
        )
    content_type: FilterExpression | None = kwargs.pop("content_type", None)
    if content_type is not None and not is_static_expression(content_type):
        raise template.TemplateSyntaxError(
            f"{tag_name} must be passed a static string ('css' or 'js') for 'content_type' (encountered variable '{content_type.var}')"
        )
    inline: FilterExpression | None = kwargs.pop("inline", None)
    if inline is not None and not is_static_expression(inline):
        raise template.TemplateSyntaxError(
            f"{tag_name} must be passed a static value of `True` or `False` for 'inline' (encountered variable '{inline.var}')"
        )
    html_attrs = {}
    for k, v in list(kwargs.items()):
        if k.startswith("html_"):
            html_attrs[k[5:]] = v
            kwargs.pop(k)
    if kwargs:
        raise template.TemplateSyntaxError(f"{tag_name} received unknown kwargs: {', '.join(kwargs.keys())}")
    # context used to resolve static expressions
    static_context = Context()
    content_type = content_type.resolve(static_context) if content_type else None
    bundler = get_bundler()
    resolver_context = ResolveContext(bundler.root_dir, parser.origin.name if parser.origin else None)
    filename = bundler.resolve_path(args[0].resolve(static_context), resolver_context)
    return BundlerEmbedAssetNode(
        filename,
        parser.origin,
        target_var=target_var,
        content_type=content_type,
        inline=inline,
        html_attrs=html_attrs,
    )


@register.simple_tag()
def bundler_embed_collected_assets():
    """Add tags to header for assets required in page

    This works with :class:`~alliance_platform.frontend.bundler.context.BundlerAssetContext` to collect all the assets used
    within a template. See :class:`~alliance_platform.frontend.bundler.middleware.BundlerAssetContextMiddleware` for how
    this context is created for you in Django views.

    Because each asset must specify asset paths statically, this tag can retrieve assets from ``BundlerAssetContext``
    and embed the required tags before the rest of the template is rendered.

    Some existing assets are those created by the :func:`~alliance_platform.frontend.templatetags.vanilla_extract.stylesheet`,
    :func:`~alliance_platform.frontend.templatetags.react.component`, or :func:`~alliance_platform.frontend.templatetags.bundler.bundler_embed`
    tags. See the individual implementations for options that may influence how they are embedded (e.g. the ``inline``
    option provided by ``bundler_embed``).

    :data:`~alliance_platform.frontend.bundler.context.BundlerAssetContext.html_target` will control whether scripts are included
    and whether CSS is outputted in line in ``style`` tags or linked externally.

    Generally, this tag should be used in the ``<head>`` of the HTML document. All script tags are non-blocking by default.
    """
    asset_context = BundlerAssetContext.get_current()
    return asset_context.register_embed_collected_assets_tag()


@register.simple_tag()
def bundler_dev_checks():
    """Performs dev specific checks and may render some HTML to communicate messages to user

    Currently check if the dev server is running for this project, and if not displays an error.

    Error will be logged to Django dev console. In addition, an error icon and toggleable modal message will be shown
    in the HTML unless :data:`~alliance_platform.frontend.settings.AlliancePlatformFrontendSettingsType.BUNDLER_DISABLE_DEV_CHECK_HTML` is set.
    """
    bundler = get_bundler()
    if not bundler.is_development():
        return ""
    check = bundler.check_dev_server()
    if not check.is_ok():
        if not check.is_running:
            warnings.warn("Bundler dev server not running; run `yarn dev` to start")
        elif check.is_wrong_server():
            warnings.warn(
                f"Bundler dev server was found but it's for project {check.project_dir}. You likely need to run `yarn dev` under {bundler.root_dir}"
            )
        elif check.read_timeout:
            warnings.warn(
                "Received ReadTimeout from dev server check; dev server is likely running but no response was received within timeout to verify"
            )
        if ap_frontend_settings.BUNDLER_DISABLE_DEV_CHECK_HTML:
            return ""
        return get_template("bundler_dev_check.html").render({"check": check})
    return ""
