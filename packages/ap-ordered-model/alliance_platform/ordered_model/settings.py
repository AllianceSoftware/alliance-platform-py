from typing import TYPE_CHECKING
from typing import TypedDict

from alliance_platform.base_settings import AlliancePlatformSettingsBase

if TYPE_CHECKING:
    pass


class AlliancePlatformOrderedModelSettingsType(TypedDict, total=False):
    """Settings for the Ordered Model package of the Alliance Platform
    These can be set in the Django settings file under the ``ALLIANCE_PLATFORM`` key:
    .. code-block:: python
        ALLIANCE_PLATFORM = {
            "ORDERED_MODEL": {
                # settings go here
            }
        }
    """
    pass


class AlliancePlatformOrderedModelSettings(AlliancePlatformSettingsBase):
    pass


ap_ordered_model_settings = AlliancePlatformOrderedModelSettings(
    "ORDERED_MODEL",
)
