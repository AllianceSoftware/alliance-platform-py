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


class AlliancePlatformStorageSettings(AlliancePlatformSettingsBase):
    pass


# TODO: Currently no settings - I'm anticipating adding some before first release. If this doesn't happen, we can
# remove storage settings entirely.
DEFAULTS: Any = {}

ap_storage_settings = AlliancePlatformStorageSettings(
    "STORAGE",
    defaults=DEFAULTS,  # type: ignore[has-type]
)
