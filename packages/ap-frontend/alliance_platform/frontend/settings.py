from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Pattern
from typing import TypedDict
from typing import Union

from alliance_platform.base_settings import AlliancePlatformSettingsBase
from django.utils.module_loading import import_string

if TYPE_CHECKING:
    from .bundler.base import BaseBundler
    from .prop_handlers import ComponentProp


class AlliancePlatformFrontendSettingsType(TypedDict, total=False):
    PRODUCTION_DIR: Path
    REACT_PROP_HANDLERS: str | list[type["ComponentProp"]]
    DEBUG_COMPONENT_OUTPUT: bool
    BUNDLER: Union[str, "BaseBundler"]
    EXTRACT_ASSETS_EXCLUDE_DIRS: tuple[Path | str, Pattern[str]]
    BUNDLER_DISABLE_DEV_CHECK_HTML: bool | None
    SSR_GLOBAL_CONTEXT_RESOLVER: str | None
    NODE_MODULES_DIR: Path | str
    REACT_RENDER_COMPONENT_FILE: Path | str


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
    #: The bundler to use. Currntly
    BUNDLER: "BaseBundler"
    #: Directories to exclude from asset extraction. By default, all directories returned by ``get_app_template_dirs("templates")`` will be inspected.
    EXTRACT_ASSETS_EXCLUDE_DIRS: tuple[Path | str, Pattern[str]]
    #: Disable the HTML outputted by ``bundler_dev_checks``. This can be useful if you want the check on generally in a project, but specific developers may wish to disable it.
    BUNDLER_DISABLE_DEV_CHECK_HTML: bool
    #: Set to a dotted path to a function that will be called to resolve the global context for SSR. This function should return a dictionary of values to be passed to the SSR renderer under the `globalContext` key.
    SSR_GLOBAL_CONTEXT_RESOLVER: str | None
    #: File that is used to render React components using the ``react`` tag. This file should export a function named ``renderComponent`` and a function ``createElementWithProps``.
    REACT_RENDER_COMPONENT_FILE: Path

    def check_settings(self):
        # TODO: Implement checks on required settings
        pass


IMPORT_STRINGS = [
    "REACT_PROP_HANDLERS",
    "BUNDLER",
]

DEFAULTS = {
    "REACT_PROP_HANDLERS": "alliance_platform.frontend.prop_handlers.default_prop_handlers",
    "DEBUG_COMPONENT_OUTPUT": False,
    "EXTRACT_ASSETS_EXCLUDE_DIRS": tuple(),
    "BUNDLER_DISABLE_DEV_CHECK_HTML": True,
    "SSR_GLOBAL_CONTEXT_RESOLVER": None,
    "REACT_RENDER_COMPONENT_FILE": None,
}


ap_frontend_settings = AlliancePlatformFrontendSettings(
    "FRONTEND", import_strings=IMPORT_STRINGS, defaults=DEFAULTS
)
