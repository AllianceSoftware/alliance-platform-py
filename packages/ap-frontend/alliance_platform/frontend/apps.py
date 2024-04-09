from alliance_platform.frontend.settings import ap_frontend_settings
from django.apps.config import AppConfig


class AlliancePlatformFrontendConfig(AppConfig):
    name = "alliance_platform.frontend"
    verbose_name = "Alliance Platform Frontend"
    label = "alliance_platform_frontend"

    def ready(self):
        ap_frontend_settings.check_settings()
