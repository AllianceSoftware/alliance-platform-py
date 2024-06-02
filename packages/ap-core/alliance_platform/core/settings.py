from pathlib import Path
from typing import TypedDict

from alliance_platform.base_settings import AlliancePlatformSettingsBase
from alliance_platform.base_settings import LazySetting


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


class AlliancePlatformCoreSettings(AlliancePlatformSettingsBase):
    PROJECT_DIR: Path
    CACHE_DIR: Path


ap_core_settings = AlliancePlatformCoreSettings(
    "CORE",
    defaults=dict(CACHE_DIR=LazySetting(lambda: ap_core_settings.PROJECT_DIR / ".alliance-platform")),  # type: ignore[has-type]
)
