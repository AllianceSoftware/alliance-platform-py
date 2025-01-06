from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Pattern
from typing import TypedDict
from typing import Union

from alliance_platform.base_settings import AlliancePlatformSettingsBase
from django.utils.module_loading import import_string

if TYPE_CHECKING:
    from .bundler.asset_registry import FrontendAssetRegistry
    from .bundler.base import BaseBundler
    from .prop_handlers import ComponentProp


class AlliancePlatformFrontendSettingsType(TypedDict, total=False):
    """The type of the settings for the frontend of the Alliance Platform.

    You can set these in your django settings like::

        from pathlib import Path
        from typing import TypedDict
        from alliance_platform.codegen.settings import AlliancePlatformCodegenSettingsType
        from alliance_platform.core.settings import AlliancePlatformCoreSettingsType

        # What you define here depends on your setup
        PROJECT_DIR = Path(__file___).parent.parent

        # What you define here depends on which Alliance Platform modules you are using. At minimum, you need to include "CORE".
        class AlliancePlatformSettings(TypedDict):
            CORE: AlliancePlatformCoreSettingsType
            CODEGEN: AlliancePlatformCodegenSettingsType

        ALLIANCE_PLATFORM: AlliancePlatformSettings = {
            "CORE": {
                "PROJECT_DIR": PROJECT_DIR,
            },
            "FRONTEND": {
                "PRODUCTION_DIR": PROJECT_DIR / "frontend/build",
            }
        }

    Below are the valid keys for ``ALLIANCE_PLATFORM["FRONTEND"]``:
    """

    #: The bundler to use as either a string import path or the class instance itself
    BUNDLER: Union[str, "BaseBundler"]
    #: If true, the React template tag will include a more readable debug output in the HTML in a comment
    DEBUG_COMPONENT_OUTPUT: bool
    #: The asset registry for the bundler. This is used to add additional assets to the bundler that are not automatically discovered.
    #: This can be a string import path to the registry or the registry itself.
    FRONTEND_ASSET_REGISTRY: Union[str, "FrontendAssetRegistry"]
    #: A list of either ``re.Pattern`` or a :class:`~pathlib.Path`. If a template directory matches any entry it will be excluded from :class:`extract_frontend_assets <alliance_platform.frontend.management.commands.extract_frontend_assets.Command>`.
    #:
    #: If a :class:`~pathlib.Path` is used it will be checked if the directory starts with that path. Otherwise a ``re.Pattern`` will exclude a directory if it matches.
    EXTRACT_ASSETS_EXCLUDE_DIRS: tuple[Path | str, Pattern[str]]
    #: If set to a truthy value :func:`~alliance_platform.frontend.templatetags.bundler.bundler_dev_checks` will not display any HTML error, the error will only be available in the Django dev console.
    BUNDLER_DISABLE_DEV_CHECK_HTML: bool | None
    #: The path to the node_modules directory. This is used by ViteBundler to resolve optimized deps, and extract_frontend_assets to determine when an import comes from node_modules directly. It is used
    #: by some codegen post processors to run node scripts (e.g. prettier or eslint). It is not used in production, so the directory does not need to exist in production.
    NODE_MODULES_DIR: Path | str
    #: The directory production assets exists in. This directory should include the Vanilla Extract mappings.
    PRODUCTION_DIR: Path
    #: Any custom prop handlers to use for react components. This can be a string import path to a list of prop handlers, or the list directly.
    REACT_PROP_HANDLERS: str | list[type["ComponentProp"]]
    #: File that is used to render React components using the ``react`` tag. This file should export a function named ``renderComponent`` and a function ``createElement`` (this can just be re-exported from React).
    REACT_RENDER_COMPONENT_FILE: Path | str
    #: Set to a dotted path to a function that will be called to resolve the global context for SSR. This function should return a dictionary of values to be passed to the SSR renderer under the `globalContext` key.
    SSR_GLOBAL_CONTEXT_RESOLVER: str | None
    #: The limit to apply for code format requests in development mode. This is limited to 1mb by default; anything above that will not be formatted. This is only
    #: applicable to dev mode where code is formatted to make debugging easier when viewing the source.
    DEV_CODE_FORMAT_LIMIT: int | None
    #: This is the timeout to apply for code format requests in development mode. This is limited to 1 seconds by default. The only time you should need to
    #: tweak this is if you are attempting to debug issues with a large piece of code; in which case you likely need to increase ``DEV_CODE_FORMAT_LIMIT`` as well.
    DEV_CODE_FORMAT_TIMEOUT: int | None


def maybe_import_string(val: Any | None):
    """
    If the given setting is a string import notation,
    then perform the necessary import or imports.
    """
    if val is None:
        return None
    elif isinstance(val, str):
        return import_string(val)
    return val


class AlliancePlatformFrontendSettings(AlliancePlatformSettingsBase):
    """
    A settings object that allows alliance_platform.frontend settings to be accessed as
    properties. For example:

        from alliance_platform.frontend.settings import ap_frontend_settings
        print(ap_frontend_settings.PRODUCTION_DIR)

    Any setting with string import paths will be automatically resolved
    and return the class, rather than the string literal.

    This class is based off of the django-rest-framework settings module
    """

    #: The directory production assets exists in. This directory should include the Vanilla Extract mappings.
    PRODUCTION_DIR: Path
    #: The path to the node_modules directory. This is used by ViteBundler to resolve optimized deps, and extract_frontend_assets to determine when an import comes from node_modules directly.
    NODE_MODULES_DIR: Path
    #: Any custom prop handlers to use for react components
    REACT_PROP_HANDLERS: list[type["ComponentProp"]]
    #: If true, the React template tag will include a more readable debug output in the HTML in a comment
    DEBUG_COMPONENT_OUTPUT: bool
    #: The asset registry for the bundler. This is used to add additional assets to the bundler that are not automatically discovered.
    FRONTEND_ASSET_REGISTRY: "FrontendAssetRegistry"
    #: The bundler to use
    BUNDLER: "BaseBundler"
    #: Directories to exclude from asset extraction. By default, all directories returned by ``get_app_template_dirs("templates")`` will be inspected.
    EXTRACT_ASSETS_EXCLUDE_DIRS: tuple[Path | str, Pattern[str]]
    #: Disable the HTML outputted by ``bundler_dev_checks``. This can be useful if you want the check on generally in a project, but specific developers may wish to disable it.
    BUNDLER_DISABLE_DEV_CHECK_HTML: bool
    #: Set to a dotted path to a function that will be called to resolve the global context for SSR. This function should return a dictionary of values to be passed to the SSR renderer under the `globalContext` key.
    SSR_GLOBAL_CONTEXT_RESOLVER: str | None
    #: File that is used to render React components using the ``react`` tag. This file should export a function named ``renderComponent`` and a function ``createElement`` (this can just be re-exported from React).
    REACT_RENDER_COMPONENT_FILE: Path
    #: The limit to apply for code format requests in development mode. This is limited to 1mb by default; anything above that will not be formatted. This is only
    #: applicable to dev mode where code is formatted to make debugging easier when viewing the source.
    DEV_CODE_FORMAT_LIMIT: int
    #: This is the timeout to apply for code format requests in development mode. This is limited to 1 seconds by default. The only time you should need to
    #: tweak this is if you are attempting to debug issues with a large piece of code; in which case you likely need to increase ``DEV_CODE_FORMAT_LIMIT`` as well.
    DEV_CODE_FORMAT_TIMEOUT: int

    def check_settings(self):
        # TODO: Implement checks on required settings

        # Make sure registry is unlocked; this can happen in tests where settings are reloaded
        # Just modify property directly, it's for internal use only - don't want 'unlock' part of the API
        self.FRONTEND_ASSET_REGISTRY._locked = False
        # lock registry to make sure assets aren't added after startup that would be missed by
        # extract_frontend_assets
        for prop_handler in self.REACT_PROP_HANDLERS:
            self.FRONTEND_ASSET_REGISTRY.add_asset(*prop_handler.get_paths_for_bundling())
        self.FRONTEND_ASSET_REGISTRY.lock()


IMPORT_STRINGS = [
    "REACT_PROP_HANDLERS",
    "BUNDLER",
    "FRONTEND_ASSET_REGISTRY",
]

DEFAULTS = {
    "REACT_PROP_HANDLERS": "alliance_platform.frontend.prop_handlers.default_prop_handlers",
    "DEBUG_COMPONENT_OUTPUT": False,
    "EXTRACT_ASSETS_EXCLUDE_DIRS": tuple(),
    "BUNDLER_DISABLE_DEV_CHECK_HTML": True,
    "SSR_GLOBAL_CONTEXT_RESOLVER": None,
    "REACT_RENDER_COMPONENT_FILE": None,
    "DEV_CODE_FORMAT_LIMIT": 1 * 1024 * 1024,
    "DEV_CODE_FORMAT_TIMEOUT": 1,
}


ap_frontend_settings = AlliancePlatformFrontendSettings(
    "FRONTEND", import_strings=IMPORT_STRINGS, defaults=DEFAULTS
)
