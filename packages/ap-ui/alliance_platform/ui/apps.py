from alliance_platform.ui.settings import ap_ui_settings
from django.apps.config import AppConfig


class AlliancePlatformUIConfig(AppConfig):
    name = "alliance_platform.ui"
    verbose_name = "Alliance Platform UI"
    label = "alliance_platform_ui"

    def ready(self):
        ap_ui_settings.check_settings()
