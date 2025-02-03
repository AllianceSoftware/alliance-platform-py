from alliance_platform.server_choices.settings import ap_server_choices_settings
from django.apps.config import AppConfig


class AlliancePlatformServerChoicesConfig(AppConfig):
    name = "alliance_platform.server_choices"
    verbose_name = "Alliance Platform Server Choices"
    label = "alliance_platform_server_choices"

    def ready(self):
        ap_server_choices_settings.check_settings()
