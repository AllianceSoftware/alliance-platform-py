from typing import TypedDict

from alliance_platform.base_settings import AlliancePlatformSettingsBase


class AlliancePlatformPDFSettingsType(TypedDict, total=False):
    """Settings for the PDF package of the Alliance Platform
    These can be set in the Django settings file under the ``ALLIANCE_PLATFORM`` key:
    .. code-block:: python
        ALLIANCE_PLATFORM = {
            "PDF": {
                # settings go here
            }
        }
    """

    #: List of domains to whitelist in PDF renderer. You do not need to include the domain the site is served from. In dev
    #: the Vite dev server is automatically included. Defaults to allow Google fonts:
    #: ``["//fonts.googleapis.com", "//fonts.gstatic.com"]``.
    #: If updating this setting it is suggested that you keep the Google font domains whitelisted.
    #: If using ``S3AsyncUploadStorage`` and you load resources from there (eg. render images), make sure to add the
    #: storage bucket domain
    WHITELIST_DOMAINS: list[str] | None


class AlliancePlatformPDFSettings(AlliancePlatformSettingsBase):
    #: List of domains to whitelist in PDF renderer. You do not need to include the domain the site is served from. In dev
    #: the Vite dev server is automatically included. Defaults to allow Google fonts:
    #: ``["//fonts.googleapis.com", "//fonts.gstatic.com"]``.
    #: If updating this setting it is suggested that you keep the Google font domains whitelisted.
    #: If using ``S3AsyncUploadStorage`` and you load resources from there (eg. render images), make sure to add the
    #: storage bucket domain
    WHITELIST_DOMAINS: list[str]


DEFAULTS = {
    "WHITELIST_DOMAINS": [
        "//fonts.googleapis.com",
        "//fonts.gstatic.com",
    ]
}

ap_pdf_settings = AlliancePlatformPDFSettings(
    "PDF",
    defaults=DEFAULTS,
)
