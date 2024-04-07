from alliance_platform.frontend.settings import AlliancePlatformFrontendSettingsType
from django.conf import settings
from django.test import override_settings
from typing_extensions import Unpack


class override_ap_frontend_settings(override_settings):
    def __init__(self, CACHE_DIR=None, **kwargs: Unpack[AlliancePlatformFrontendSettingsType]):
        CORE = settings.ALLIANCE_PLATFORM.get("CORE", {})
        if CACHE_DIR:
            CORE["CACHE_DIR"] = CACHE_DIR
        super().__init__(
            ALLIANCE_PLATFORM={
                **settings.ALLIANCE_PLATFORM,
                "CORE": CORE,
                "FRONTEND": {**settings.ALLIANCE_PLATFORM.get("FRONTEND", {}), **kwargs},
            }
        )
