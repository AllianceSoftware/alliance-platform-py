from alliance_platform.pdf.settings import ap_pdf_settings
from django.apps.config import AppConfig


class AlliancePlatformPDFConfig(AppConfig):
    name = "alliance_platform.pdf"
    verbose_name = "Alliance Platform PDF"
    label = "alliance_platform_pdf"

    def ready(self):
        ap_pdf_settings.check_settings()
