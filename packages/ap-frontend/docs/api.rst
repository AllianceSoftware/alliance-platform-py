API
***

Utils
-----

.. autofunction:: alliance_platform.frontend.util.transform_attribute_names

.. autofunction:: alliance_platform.frontend.util.guess_node_path

.. autofunction:: alliance_platform.frontend.util.get_node_ver

Bundler
-------

.. autofunction:: alliance_platform.frontend.bundler.get_bundler

.. autoclass:: alliance_platform.frontend.bundler.base.BaseBundler
    :members:

.. autoclass:: alliance_platform.frontend.bundler.base.AssetFileEmbed
    :members:

.. autoclass:: alliance_platform.frontend.bundler.base.ResolveContext
    :members:

.. autoclass:: alliance_platform.frontend.bundler.base.PathResolver
    :members:

.. autoclass:: alliance_platform.frontend.bundler.base.RegExAliasResolver
    :members:

.. autoclass:: alliance_platform.frontend.bundler.base.SourceDirResolver
    :members:

.. autoclass:: alliance_platform.frontend.bundler.base.RelativePathResolver
    :members:

.. autoclass:: alliance_platform.frontend.bundler.asset_registry.FrontendAssetRegistry
    :members:

.. py:data:: alliance_platform.frontend.bundler.asset_registry.frontend_asset_registry

    The default registry that is used throughout the site.

.. autoclass:: alliance_platform.frontend.bundler.base.DevServerCheck
    :members:


Vite Bundler
-------------

Example setup::

    import json
    import logging
    from pathlib import Path
    from textwrap import dedent
    import time

    from django.conf import settings

    from alliance_platform.frontend.bundler.base import PathResolver
    from alliance_platform.frontend.bundler.base import RegExAliasResolver
    from alliance_platform.frontend.bundler.base import RelativePathResolver
    from alliance_platform.frontend.bundler.base import ResolveContext
    from alliance_platform.frontend.bundler.base import SourceDirResolver
    from alliance_platform.frontend.bundler.vite import ViteBundler
    from django_site.settings.base import get_env_setting

    root_dir = settings.PROJECT_DIR
    bundler_mode = settings.VITE_BUNDLER_MODE

    # This assumes the Vite server writes these files to the cache directory for you
    server_details_path = ap_core_settings.CACHE_DIR / "vite-server-address.json"
    server_state_path = ap_core_settings.CACHE_DIR / "vite-server-state.json"
    server_details = {}

    if server_details_path.exists():
        server_details = json.loads(server_details_path.read_text())

    if bundler_mode == "development" and server_details:
        # Allow switching to 'preview' mode in dev
        bundler_mode = server_details["serverType"]

    # An example of a custom resolver that will resolve paths starting with @alliancesoftware/ui or @alliancesoftware/icons to
    # the node modules directory
    class AlliancePlatformPackageResolver(PathResolver):
        """Resolves strings that begin with ``./`` or ``../`` as relative to ``context.source_path``"""

        def resolve(self, path: str, context: ResolveContext):
            if path.startswith("@alliancesoftware/ui") or path.startswith("@alliancesoftware/icons"):
                return ap_frontend_settings.NODE_MODULES_DIR / path
            return None

    def wait_for_server():
        if server_state_path.exists():
            server_details = json.loads(server_state_path.read_text())
            if server_details.get("status") == "starting":
                logger.warning(
                    "Vite server is starting... web requests will wait until this resolves before loading"
                )
                warning_logged = False
                start = time.time()
                while server_details.get("status") == "starting":
                    time.sleep(0.1)
                    server_details = json.loads(server_state_path.read_text())
                    if not warning_logged and (time.time() - start) > 10:
                        logger.warning(
                            "Vite appears to be taking a while to build. Check your `yarn dev` or `yarn preview` command is running and has not crashed"
                        )
                        warning_logged = True


    vite_bundler = ViteBundler(
        root_dir=root_dir,
        path_resolvers=[
            AlliancePlatformPackageResolver(),
            RelativePathResolver(),
            RegExAliasResolver("^/", str(settings.PROJECT_DIR) + "/"),
            # Resolve relative paths from this directory
            SourceDirResolver(root_dir / "frontend/src"),
        ],
        mode=bundler_mode,
        server_build_dir=settings.PROJECT_DIR / "frontend/server-build",
        build_dir=settings.PROJECT_DIR / "frontend/build",
        server_host=server_details.get("host", "localhost"),
        server_port=server_details.get("port", "5173"),
        server_protocol=server_details.get("protocol", "http"),
        production_ssr_url=settings.FRONTEND_PRODUCTION_SSR_URL,
        wait_for_server=wait_for_server,
    )

.. autoclass:: alliance_platform.frontend.bundler.vite.ViteBundler
    :members:

.. autoclass:: alliance_platform.frontend.bundler.vite.ViteEmbed
    :members:

.. autoclass:: alliance_platform.frontend.bundler.vite.ViteJavaScriptEmbed
    :members:

.. autoclass:: alliance_platform.frontend.bundler.vite.ViteImageEmbed
    :members:

.. autoclass:: alliance_platform.frontend.bundler.vite.ViteManifest
    :members:

    .. automethod:: __init__

.. autoclass:: alliance_platform.frontend.bundler.vite.ViteManifestAsset
    :members:

.. autoclass:: alliance_platform.frontend.bundler.vite.AssetDependencies
    :members:

SSR
----

.. autoclass:: alliance_platform.frontend.bundler.ssr.SSRSerializable
    :members:

.. autoclass:: alliance_platform.frontend.bundler.ssr.SSRCustomFormatSerializable
    :members:
    :exclude-members: serialize

.. autoclass:: alliance_platform.frontend.bundler.ssr.SSRSerializerContext
    :members:


React
-----

See :ttag:`{% component %} <component>` for more information on how to use React components in your templates.

.. autoclass:: alliance_platform.frontend.templatetags.react.ComponentNode
    :members:

.. autoclass:: alliance_platform.frontend.prop_handlers.ComponentProp
    :members:
    :inherited-members:

Default Prop Handlers
---------------------

These are the default prop handlers that are used by convert props to the correct format for the frontend when using
the :ttag:`{% component %} <component>` tag.

.. warning::

    Currently :class:`~alliance_platform.frontend.prop_handlers.DateProp`, :class:`~alliance_platform.frontend.prop_handlers.DateTimeProp`,
    :class:`~alliance_platform.frontend.prop_handlers.ZonedDateTimeProp` and :class:`~alliance_platform.frontend.prop_handlers.TimeProp`
    use the `@internationalized/date <https://react-spectrum.adobe.com/internationalized/date/index.html>`_ library to
    parse and format dates. Make sure this package is installed.

.. autoclass:: alliance_platform.frontend.prop_handlers.SetProp
    :exclude-members: __init__
.. autoclass:: alliance_platform.frontend.prop_handlers.DateProp
.. autoclass:: alliance_platform.frontend.prop_handlers.DateTimeProp
.. autoclass:: alliance_platform.frontend.prop_handlers.ZonedDateTimeProp
.. autoclass:: alliance_platform.frontend.prop_handlers.TimeProp
.. autoclass:: alliance_platform.frontend.prop_handlers.SpecialNumeric
