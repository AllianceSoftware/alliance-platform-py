from pathlib import Path
from typing import Callable
from typing import TypedDict

from alliance_platform.base_settings import AlliancePlatformSettingsBase
from alliance_platform.base_settings import LazySetting
from django.apps import AppConfig
from django.db.models import Model

RESOLVE_PERM_NAME_TYPE = Callable[[AppConfig, Model | type[Model] | None, str, bool], str]


class AlliancePlatformCoreSettingsType(TypedDict, total=False):
    """Settings for the core package of the Alliance Platform

    These can be set in the Django settings file under the ``ALLIANCE_PLATFORM`` key:

    .. code-block:: python

        ALLIANCE_PLATFORM = {
            "CORE": {
                "PROJECT_DIR": PROJECT_DIR,
            }
        }
    """

    #: The root directory of the project
    PROJECT_DIR: Path | str
    #: A directory used for caching. This is used by various packages. If not set, defaults to ``PROJECT_DIR / '.alliance-platform'``
    CACHE_DIR: Path | str | None
    #: A function used to resolve a permission name for a model and action
    RESOLVE_PERM_NAME: str | RESOLVE_PERM_NAME_TYPE


class AlliancePlatformCoreSettings(AlliancePlatformSettingsBase):
    PROJECT_DIR: Path
    CACHE_DIR: Path
    RESOLVE_PERM_NAME: RESOLVE_PERM_NAME_TYPE


DEFAULTS = dict(
    CACHE_DIR=LazySetting(lambda: ap_core_settings.PROJECT_DIR / ".alliance-platform"),
    RESOLVE_PERM_NAME="alliance_platform.core.auth.default_resolve_perm_name",
)

ap_core_settings = AlliancePlatformCoreSettings(
    "CORE",
    defaults=DEFAULTS,  # type: ignore[has-type]
    import_strings=["RESOLVE_PERM_NAME"],
)
