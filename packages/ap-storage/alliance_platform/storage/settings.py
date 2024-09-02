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


class AlliancePlatformStorageSettings(AlliancePlatformSettingsBase):
    pass


DEFAULTS = {}

ap_storage_settings = AlliancePlatformStorageSettings(
    "STORAGE",
    defaults=DEFAULTS,  # type: ignore[has-type]
)
