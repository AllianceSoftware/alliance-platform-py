from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import threading
from typing import Type
import warnings

from django.conf import settings
from django.http import HttpRequest
from django.template import Origin
from django.utils.module_loading import import_string

from ..settings import ap_frontend_settings
from . import get_bundler
from .asset_registry import FrontendAssetRegistry
from .base import AssetFileEmbed
from .base import BaseBundler
from .base import HtmlGenerationTarget
from .base import html_target_browser
from .ssr import SSRItem

GLOBAL_BUNDLER_ASSET_CONTEXT = threading.local()


class NoActiveBundlerAssetContext(Exception):
    """Thrown if :meth:`~alliance_platform.frontend.bundler.context.BundlerAssetContext.get_current` is called when no context is active"""

    pass


class UndiscoverableAssetsError(Exception):
    """Thrown if assets are used, but cannot be discovered automatically and aren't registered with the asset registry"""

    def __init__(self, paths: set[Path]):
        paths_str = "\n".join(map(str, paths))
        super().__init__(
            f"The following paths were used but cannot be auto-discovered by `extract_frontend_assets`:\n{paths_str}\n\n"
            f"To resolve add these paths to the asset registry, e.g. `frontend_asset_registry.add_asset(...paths...)`."
        )
        self.undiscoverable_assets = paths


class BundlerAsset:
    """
    A class representing an asset (e.g. script, stylesheet) that needs to be bundled.

    Each asset could have dependencies that also need to be bundled. All relevant files should be returned by
    ``get_paths_for_bundling``.

    All assets must be static so that the files that are required in production can be extracted at build time. This allows
    the bundler to know what files to compile based on usage in templates. For example a Template node must be able to
    resolve its argument when the node is constructed - it cannot depend on resolving it based on context.

    On creation, each node is added to the current context with :meth:`~alliance_platform.frontend.bundler.context.BundlerAssetContext.add_asset`.

    The :class:`~alliance_platform.frontend.bundler.context.BundlerAssetContext` can then be queried to see what assets have been used.

    :class:`extract_frontend_assets <alliance_platform.frontend.management.commands.extract_frontend_assets.Command>` uses this to work out what assets are used anywhere in the app by loading all templates. Any
    template nodes that extend ``BundlerAsset`` will be automatically added to the context.
    """

    #: The current bundler
    bundler: BaseBundler
    #: The current context. Will always be set; if no context is active then an error will be thrown on init
    bundler_asset_context: BundlerAssetContext
    #: The template origin for this asset. This is used to ensure each asset will be found at build time.
    origin: Origin

    def __init__(self, origin: Origin):
        self.origin = origin
        self.bundler = get_bundler()
        # TODO: It's possible there's use cases where we might not want to require a context. For now require it until
        # they emerge.
        self.bundler_asset_context = BundlerAssetContext.get_current()
        self.bundler_asset_context.add_asset(self)

    def get_paths_for_bundling(self) -> list[Path]:
        """Return a list of paths to files this asset requires

        These will be included in the build process - see :class:`extract_frontend_assets <alliance_platform.frontend.management.commands.extract_frontend_assets.Command>`
        """
        raise NotImplementedError

    def get_dynamic_paths_for_bundling(self) -> list[Path]:
        """Return a list of paths to files this asset used at runtime.

        This is useful for cases where it can't be determined statically what dependencies are required (e.g. based
        on the usage of a component).

        This is used by ``BundlerAssetContext`` during development to determine that any used dependencies will be
        available in production.
        """
        return []


class AssetEmbedFileQueue:
    """Queue for asset files to be embedded in a page

    Preserves order file are added in & guarantees no duplicates will be added.
    """

    items: list[AssetFileEmbed]

    def __init__(self):
        self.items = []

    def add(self, item: AssetFileEmbed):
        if item not in self.items:
            self.items.append(item)

    def is_empty(self):
        return not self.items

    def clear(self):
        self.items = []


@lru_cache
def get_ssr_global_context_resolver():
    try:
        resolver = ap_frontend_settings.SSR_GLOBAL_CONTEXT_RESOLVER
    except AttributeError:
        return None
    else:
        return None if resolver is None else import_string(resolver)


class BundlerAssetContext:
    """
    Class that acts as container for global context data for React apps and a context manager

    When called in a django request and :class:`~alliance_platform.frontend.bundler.middleware.BundlerAssetContextMiddleware` is
    used a context always available from :meth:`~alliance_platform.frontend.bundler.context.BundlerAssetContext.get_current()`.

    Usage::

        with BundlerAssetContext() as context:
            # Any templates that contain nodes that extend BundlerAsset will end up in context
            contents = render_template()
            # Post process contents to handle SSR & embedding the asset tags
            contents = context.post_process(contents)

            # Retrieve the paths for all assets that were added to the context
            context.get_asset_paths()

    Usage in a django view when :class:`~alliance_platform.frontend.bundler.middleware.BundlerAssetContextMiddleware` is active::

        context = BundlerAssetContext.get_current()
        context.get_asset_paths()
    """

    #: All the assets that have been added
    assets: list[BundlerAsset]
    #: All assets that have been queued for embedding in the final HTML
    embed_item_queue: AssetEmbedFileQueue
    #: Contains all SSRItem's that have been queued for rendering
    ssr_queue: dict[str, SSRItem]
    #: The registry to use for assets that can't be discovered automatically.
    frontend_asset_registry: FrontendAssetRegistry
    #: The target HTML is being generated for. This determines things like whether scripts are required at runtime, and
    #: whether CSS should be inlined in ``style`` tags or linked from an external file. Defaults to
    html_target: HtmlGenerationTarget
    #: If specified, no checks will be done on context exit to ensure all assets have been embedded or post processed. Useful for tests.
    skip_checks: bool

    # Will only be set if ``bundler_embed_collected_assets`` is used
    embed_collected_assets_tag_placeholder: str | None

    #: Will be set if used within ``BundlerAssetContextMiddleware``. In other contexts may be unavailable
    request: HttpRequest | None

    def __init__(
        self,
        *,
        frontend_asset_registry: FrontendAssetRegistry | None = None,
        html_target=html_target_browser,
        skip_checks=False,
        request: HttpRequest | None = None,
    ):
        if frontend_asset_registry is None:
            frontend_asset_registry = ap_frontend_settings.FRONTEND_ASSET_REGISTRY
        self.request = request
        self.skip_checks = skip_checks
        self.html_target = html_target
        self.frontend_asset_registry = frontend_asset_registry
        self.assets = []
        self.ssr_queue = {}
        self.current_id = 0
        self.id_prefix = f"{threading.get_ident()}_{id(self)}_"
        self.is_middleware_registered = (
            "alliance_platform.frontend.bundler.middleware.BundlerAssetContextMiddleware"
            in settings.MIDDLEWARE
        )
        self.embed_item_queue = AssetEmbedFileQueue()
        self.embed_collected_assets_tag_placeholder = None

    def add_asset(self, asset: BundlerAsset):
        """Add an asset to the current context"""
        if asset not in self.assets:
            self.assets.append(asset)

    def queue_embed_file(self, item: AssetFileEmbed):
        """Queues an asset to be embedded in the final HTML

        The actual embedding and insertion into the HTML happens in :meth:`~alliance_platform.frontend.bundler.context.BundlerAssetContext.post_process`,
        which is called by :class:`~alliance_platform.frontend.bundler.middleware.BundlerAssetContextMiddleware` which
        relies on :meth:`~alliance_platform.frontend.templatetags.bundler.bundler_embed_collected_assets` being used in the template.
        Typically, this tag would exist in any base templates that are used for all pages.

        ``item`` is responsible for generating the actual HTML to embed which typically depends on the bundler.
        """
        self.embed_item_queue.add(item)

    def get_asset_paths(self, of_type: Type[BundlerAsset] | None = None) -> list[Path]:
        """Return the paths for assets used by assets added to this context"""
        asset_paths = []
        for asset in self.get_assets(of_type):
            for path in asset.get_paths_for_bundling():
                # we do it like this rather than Set so order is preserved
                if path not in asset_paths:
                    asset_paths.append(path)
        return asset_paths

    def get_assets(self, of_type: Type[BundlerAsset] | None = None) -> list[BundlerAsset]:
        """Get assets that have been added to context, optionally filtered by ``of_type``

        Args:
            of_type: If provided only assets of this type will be returned
        """
        if of_type:
            return [asset for asset in self.assets if isinstance(asset, of_type)]
        return self.assets

    @classmethod
    def get_current(cls) -> BundlerAssetContext:
        """Get the current BundlerAssetContext or raise :class:`~alliance_platform.frontend.bundler.context.NoActiveBundlerAssetContext` if none

        When called in a django request and :class:`~alliance_platform.frontend.bundler.middleware.BundlerAssetContextMiddleware` is
        used one will always be available.
        """
        if not hasattr(GLOBAL_BUNDLER_ASSET_CONTEXT, "contexts") or not GLOBAL_BUNDLER_ASSET_CONTEXT.contexts:
            raise NoActiveBundlerAssetContext("No context currently active")
        return GLOBAL_BUNDLER_ASSET_CONTEXT.contexts[-1]

    def queue_ssr(self, item: SSRItem) -> str:
        """Queue an item for server side rendering

        Note that if the current bundler does not support SSR, this will have no effect. You can safely call it still
        and output the placeholder HTML comment, it just will not be replaced with anything.

        Args:
            item: The item to render

        Returns:
            A string which is the placeholder that should be outputted in the HTML. It will be replaced by
            :class:`~alliance_platform.frontend.bundler.middleware.BundlerAssetContextMiddleware`.
        """
        if not get_bundler().is_ssr_enabled():
            # Include a comment to make it clear SSR is not enabled to assist debugging
            return "<!-- SSR NOT ENABLED -->"
        if not self.is_middleware_registered:
            raise ValueError(
                "`queue_ssr` cannot be used without `BundlerAssetContextMiddleware`. Add 'alliance_platform.frontend.bundler.middleware.BundlerAssetContextMiddleware' to `MIDDLEWARE`."
            )
        placeholder = f"<!-- ___SSR_PLACEHOLDER_{len(self.ssr_queue)}___ -->"
        self.ssr_queue[placeholder] = item
        return placeholder

    def generate_id(self) -> str:
        """Generate an ID that is guaranteed to be unique for this context

        This can be used for generating ID's to use in HTML, e.g. for container rendering React components into
        """
        next_id = f"{self.id_prefix}{self.current_id}"
        self.current_id += 1
        return next_id

    def __enter__(self):
        if not hasattr(GLOBAL_BUNDLER_ASSET_CONTEXT, "contexts"):
            GLOBAL_BUNDLER_ASSET_CONTEXT.contexts = []
        GLOBAL_BUNDLER_ASSET_CONTEXT.contexts.append(self)
        self.id_prefix = f"{self.id_prefix}_{len(GLOBAL_BUNDLER_ASSET_CONTEXT.contexts)}_"
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        GLOBAL_BUNDLER_ASSET_CONTEXT.contexts.pop()
        if exc_type or self.skip_checks:
            # Don't do any checks if there was an error
            return

        # Check all assets will be included in the production build
        unknown_assets = set()

        from ..management.commands.extract_frontend_assets import get_all_templates_files

        known_templates = get_all_templates_files()

        cleared_cache = False
        for asset in self.assets:
            origin_name = Path(asset.origin.name)
            if not asset.origin.template_name or origin_name not in known_templates:
                # handle case where new template has been added without server restart
                if not cleared_cache and asset.origin.template_name:
                    get_all_templates_files.cache_clear()
                    known_templates = get_all_templates_files()
                    cleared_cache = True
                    if Path(asset.origin.name) in known_templates:
                        continue
                unknown_assets.update(
                    self.frontend_asset_registry.get_unknown(*asset.get_paths_for_bundling())
                )
            unknown_assets.update(
                self.frontend_asset_registry.get_unknown(*asset.get_dynamic_paths_for_bundling())
            )
        if unknown_assets:
            raise UndiscoverableAssetsError(unknown_assets)

        if self.requires_post_processing():
            raise ValueError(f"{exc_type} BundlerAssetContext.post_process() was not called but is required")

    def register_embed_collected_assets_tag(self) -> str:
        """For use by ``bundler_embed_collected_assets`` only

        This is used by the template tag to register that it has been used, and to get the placeholder string to
        write in the initial HTML that will then be replaced in ``post_process``.
        """
        if self.embed_collected_assets_tag_placeholder:
            raise ValueError(
                "Duplicate {% bundler_embed_collected_assets %} tags detected. Only one such tag should exist."
            )
        # this is the string the template tag should render. It's then replaced in ``post_process``
        self.embed_collected_assets_tag_placeholder = "__BundlerAssetContext__embed_placeholder__"
        return self.embed_collected_assets_tag_placeholder

    def requires_post_processing(self):
        """Check if ``post_process`` needs to be called"""
        return not self.embed_item_queue.is_empty() or self.ssr_queue

    def abort_post_process(self):
        """Called when ``post_process`` can't be called (e.g. on a request where content-type isn't text/html)"""
        self.embed_item_queue.clear()
        self.ssr_queue = {}

    def post_process(self, content: str):
        """Given the HTML content, post process it to embed assets and render server side rendered components

        This is typically called by :class:`~alliance_platform.frontend.bundler.middleware.BundlerAssetContextMiddleware`, but can
        be called directly if rendering templates of other purposes such as emails of PDFs. ``content`` should be the
        full HTML content of the page, including the ``<head>`` and ``<body>`` tags. This function will handle embedding
        any necessary assets based on calls to :meth:`~alliance_platform.frontend.bundler.context.BundlerAssetContext.queue_embed_file`
        as well as any server side rendered components queued with :meth:`~alliance_platform.frontend.bundler.context.BundlerAssetContext.queue_ssr`.

        This should be the last step before the HTML is outputted to the client.
        """
        try:
            if self.ssr_queue:
                from .ssr import BundlerAssetServerSideRenderer

                global_context = {}
                if self.request:
                    global_context["currentUrl"] = self.request.build_absolute_uri()
                    if resolver := get_ssr_global_context_resolver():
                        global_context.update(resolver(self.request))
                content = BundlerAssetServerSideRenderer(self.ssr_queue).process(content, global_context)
            if not self.embed_item_queue.is_empty():
                if not self.embed_collected_assets_tag_placeholder:
                    warnings.warn(
                        "There are some assets that require embedding but no {% bundler_embed_collected_assets %} exists in the current template."
                    )
                else:
                    tags = []
                    for item in self.embed_item_queue.items:
                        code = item.generate_code(self.html_target)
                        if code:
                            tags.append(code)
                    content = content.replace(self.embed_collected_assets_tag_placeholder, "\n".join(tags))
            elif self.embed_collected_assets_tag_placeholder:
                # no assets to embed but we need to remove the placeholder
                content = content.replace(self.embed_collected_assets_tag_placeholder, "")
            return content
        finally:
            self.embed_item_queue.clear()
            self.ssr_queue = {}
