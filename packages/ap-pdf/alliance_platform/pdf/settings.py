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


class AlliancePlatformPDFSettings(AlliancePlatformSettingsBase):
    pass


DEFAULTS = {}

ap_pdf_settings = AlliancePlatformPDFSettings(
    "PDF",
    defaults=DEFAULTS,  # type: ignore[has-type]
)
