from alliance_platform.codegen.settings import ap_codegen_settings
from django.apps.config import AppConfig


class AlliancePlatformCodegenConfig(AppConfig):
    name = "alliance_platform.codegen"
    verbose_name = "Alliance Platform Codegen"
    label = "alliance_platform_codegen"

    def ready(self):
        ap_codegen_settings.check_settings()
