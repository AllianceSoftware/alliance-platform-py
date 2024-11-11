from alliance_platform.core.settings import AlliancePlatformCoreSettingsType
from django.conf import settings
from django.test import override_settings
from typing_extensions import Unpack


class override_ap_core_settings(override_settings):
    def __init__(self, **kwargs: Unpack[AlliancePlatformCoreSettingsType]):
        CORE = settings.ALLIANCE_PLATFORM.get("CORE", {})
        super().__init__(
            ALLIANCE_PLATFORM={
                **settings.ALLIANCE_PLATFORM,
                "CORE": {
                    **CORE,
                    **kwargs,
                },
            }
        )
