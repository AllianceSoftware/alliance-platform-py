from alliance_platform.frontend.checks import FRONTEND_BUILD_CHECK_TAG
from alliance_platform.ui.settings import ap_ui_settings
from django.apps.config import AppConfig
from django.core.checks import register


class AlliancePlatformUIConfig(AppConfig):
    name = "alliance_platform.ui"
    verbose_name = "Alliance Platform UI"
    label = "alliance_platform_ui"

    def ready(self):
        # Imported here as it loads the static components
        from alliance_platform.ui.checks import check_static_contract

        ap_ui_settings.check_settings()
        register(check_static_contract, FRONTEND_BUILD_CHECK_TAG)
