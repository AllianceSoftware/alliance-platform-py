from alliance_platform.storage.settings import ap_storage_settings
from django.apps.config import AppConfig


class AlliancePlatformStorageConfig(AppConfig):
    name = "alliance_platform.storage"
    verbose_name = "Alliance Platform Storage"
    label = "alliance_platform_storage"

    def ready(self):
        ap_storage_settings.check_settings()
