from typing import TypedDict

from alliance_platform.base_settings import AlliancePlatformSettingsBase


class AlliancePlatformServerChoicesSettingsType(TypedDict, total=False):
    """Settings for the Server Choices package of the Alliance Platform
    These can be set in the Django settings file under the ``ALLIANCE_PLATFORM`` key:
    .. code-block:: python
        ALLIANCE_PLATFORM = {
            "SERVER_CHOICES": {
                # settings go here
            }
        }
    """


class AlliancePlatformServerChoicesSettings(AlliancePlatformSettingsBase):
    pass


DEFAULTS = {}

ap_server_choices_settings = AlliancePlatformServerChoicesSettings(
    "SERVER_CHOICES",
    defaults=DEFAULTS,
)
