from pathlib import Path
from typing import TypedDict

from alliance_platform.base_settings import AlliancePlatformSettingsBase
from alliance_platform.base_settings import LazySetting


class AlliancePlatformCoreSettingsType(TypedDict, total=False):
    PROJECT_DIR: Path | str
    CACHE_DIR: Path | str | None


class AlliancePlatformCoreSettings(AlliancePlatformSettingsBase):
    PROJECT_DIR: Path
    CACHE_DIR: Path


# TODO: CACHE_DIR needs to default to PROJECT_DIR / ".alliance-platform"
ap_core_settings = AlliancePlatformCoreSettings(
    "CORE",
    defaults=dict(CACHE_DIR=LazySetting(lambda: ap_core_settings.PROJECT_DIR / ".alliance-platform")),  # type: ignore[has-type]
)
