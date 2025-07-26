from typing import TYPE_CHECKING
from typing import TypedDict

from alliance_platform.base_settings import AlliancePlatformSettingsBase

if TYPE_CHECKING:
    pass


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

    #: The default page size to use for server choices
    PAGE_SIZE: int


class AlliancePlatformServerChoicesSettings(AlliancePlatformSettingsBase):
    #: The default page size to use for server choices.
    PAGE_SIZE: int


DEFAULTS = {
    "PAGE_SIZE": 20,
}

ap_server_choices_settings = AlliancePlatformServerChoicesSettings(
    "SERVER_CHOICES",
    defaults=DEFAULTS,
)
