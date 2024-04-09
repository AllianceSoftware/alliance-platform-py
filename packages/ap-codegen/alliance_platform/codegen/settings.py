from pathlib import Path
from typing import TYPE_CHECKING
from typing import TypedDict
from typing import cast

from alliance_platform.base_settings import AlliancePlatformSettingsBase
from alliance_platform.base_settings import LazySetting
from alliance_platform.core.settings import ap_core_settings

if TYPE_CHECKING:
    from .registry import ArtifactPostProcessor


class AlliancePlatformCodegenSettingsType(TypedDict, total=False):
    #: Root directory for frontend code. When imports are defined as a ``Path`` they will be resolved relative to this directory. Defaults to "CORE.PROJECT_DIR".
    JS_ROOT_DIR: Path | str | None
    TEMP_DIR: Path | str | None
    POST_PROCESSORS: list[str]


IMPORT_STRINGS = ["POST_PROCESSORS"]

DEFAULTS = {
    "TEMP_DIR": None,
    "POST_PROCESSORS": cast(list["ArtifactPostProcessor"], []),
    "JS_ROOT_DIR": LazySetting(lambda: ap_core_settings.PROJECT_DIR),
}


class AlliancePlatformCodegenSettings(AlliancePlatformSettingsBase):
    #: Root directory for frontend code. When imports are defined as a ``Path`` they will be resolved relative to this directory.
    JS_ROOT_DIR: Path
    TEMP_DIR: Path | None
    POST_PROCESSORS: list["ArtifactPostProcessor"]


ap_codegen_settings = AlliancePlatformCodegenSettings(
    "CODEGEN", defaults=DEFAULTS, import_strings=IMPORT_STRINGS
)
