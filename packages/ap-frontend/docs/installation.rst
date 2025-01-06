Installation
------------

Install the ``alliance_platform_frontend`` and ``alliance_platform_codegen`` packages:

.. code-block:: bash

    poetry add alliance_platform_codegen alliance_platform_frontend

Add ``alliance_platform.frontend`` and ``alliance_platform.codegen`` to your ``INSTALLED_APPS``:

.. code-block:: python

    INSTALLED_APPS = [
        ...
        'alliance_platform.codegen',
        'alliance_platform.frontend',
        ...
    ]

Configuration
-------------

See the :doc:`settings` documentation for details about each of the available settings.

.. code-block:: python

    from alliance_platform.core.settings import AlliancePlatformCoreSettingsType
    from alliance_platform.codegen.settings import AlliancePlatformCodegenSettingsType
    from alliance_platform.frontend.settings import AlliancePlatformFrontendSettingsType
    from alliance_platform.frontend.util import guess_node_path

    # PROJECT_DIR  should be set to the root of your project

    NODE_PATH = guess_node_path(PROJECT_DIR / ".nvmrc") or "node"
    NODE_MODULES_DIR = PROJECT_DIR / "node_modules"

    class AlliancePlatformSettings(TypedDict):
        CORE: AlliancePlatformCoreSettingsType
        FRONTEND: AlliancePlatformFrontendSettingsType
        CODEGEN: AlliancePlatformCodegenSettingsType


    ALLIANCE_PLATFORM: AlliancePlatformSettings = {
        "CORE": {"PROJECT_DIR": PROJECT_DIR},
        "CODEGEN": {
            # Omitted for brevity. See codegen docs.
        },
        "FRONTEND": {
            "FRONTEND_ASSET_REGISTRY": "django_site.asset_registry.frontend_asset_registry",
            "REACT_RENDER_COMPONENT_FILE": PROJECT_DIR / "frontend/src/renderComponent.tsx",
            "NODE_MODULES_DIR": NODE_MODULES_DIR,
            "EXTRACT_ASSETS_EXCLUDE_DIRS": (BASE_DIR / "codegen", re.compile(r".*/site-packages/.*")),
            "BUNDLER": "django_site.bundler.vite_bundler",
            # Can be set to disable the HTML embedded when dev server not running. Messages still logged to django dev console.
            "BUNDLER_DISABLE_DEV_CHECK_HTML": bool(
                _strtobool(get_env_setting("FRONTEND_BUNDLER_DISABLE_DEV_CHECK_HTML", "0"))
            ),
            # In dev, you should set this to ``True``.
            "DEBUG_COMPONENT_OUTPUT": False,
            # Any custom prop handlers for your project
            "REACT_PROP_HANDLERS": "django_site_core.prop_handlers.prop_handlers",
            "SSR_GLOBAL_CONTEXT_RESOLVER": "django_site.frontend.ssr_global_context_resolver",
            "PRODUCTION_DIR": PROJECT_DIR / "frontend/build",
        },
    }

In the ``MIDDLEWARE`` setting, add the ``BundlerAssetContextMiddleware`` middleware. This is used by tags like
:ttag:`component` and :ttag:`bundler_embed`.

.. code-block:: python

    MIDDLEWARE = [
        ...
        "alliance_platform.frontend.bundler.middleware.BundlerAssetContextMiddleware",
        ...
    ]
