from typing import Any
from typing import TypedDict

from alliance_platform.base_settings import AlliancePlatformSettingsBase


class AlliancePlatformStorageSettingsType(TypedDict, total=False):
    """Settings for the Storage package of the Alliance Platform

    These can be set in the Django settings file under the ``ALLIANCE_PLATFORM`` key:

    .. code-block:: python

        ALLIANCE_PLATFORM = {
            "STORAGE": {
                # settings go here
            }
        }
    """

    #: Number of seconds a generated upload URL is valid for by default. Defaults to 3600.
    UPLOAD_URL_EXPIRY: int | None
    #: Number of seconds a generated download URL is valid for by default. Defaults to 3600.
    DOWNLOAD_URL_EXPIRY: int | None


class AlliancePlatformStorageSettings(AlliancePlatformSettingsBase):
    #: Number of seconds a generated upload URL is valid for by default. Defaults to 3600.
    UPLOAD_URL_EXPIRY: int
    #: Number of seconds a generated download URL is valid for by default. Defaults to 3600.
    DOWNLOAD_URL_EXPIRY: int


DEFAULTS: Any = {
    "UPLOAD_URL_EXPIRY": 3600,
    "DOWNLOAD_URL_EXPIRY": 3600,
}

ap_storage_settings = AlliancePlatformStorageSettings(
    "STORAGE",
    defaults=DEFAULTS,
)
