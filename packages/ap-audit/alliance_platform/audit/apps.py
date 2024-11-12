from alliance_platform.audit.settings import ap_audit_settings
from django.apps.config import AppConfig


class AlliancePlatformAuditConfig(AppConfig):
    name = "alliance_platform.audit"
    verbose_name = "Alliance Platform Audit"
    label = "alliance_platform_audit"

    def ready(self):
        ap_audit_settings.check_settings()
