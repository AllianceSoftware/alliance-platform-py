from alliance_platform.ordered_model.settings import ap_ordered_model_settings
from django.apps.config import AppConfig


class AlliancePlatformOrderedModelConfig(AppConfig):
    name = "alliance_platform.ordered_model"
    verbose_name = "Alliance Platform Ordered Model"
    label = "alliance_platform_ordered_model"

    def ready(self):
        ap_ordered_model_settings.check_settings()
