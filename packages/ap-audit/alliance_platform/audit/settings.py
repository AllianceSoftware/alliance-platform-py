from typing import TypedDict

from alliance_platform.base_settings import AlliancePlatformSettingsBase


class AlliancePlatformAuditSettingsType(TypedDict, total=False):
    """Settings for the Audit package of the Alliance Platform
    These can be set in the Django settings file under the ``ALLIANCE_PLATFORM`` key:
    .. code-block:: python
        ALLIANCE_PLATFORM = {
            "AUDIT": {
                # settings go here
            }
        }
    """


class AlliancePlatformAuditSettings(AlliancePlatformSettingsBase):
    pass


DEFAULTS = {"AUDIT_LIST_PERM_ACTION": "audit"}
ap_audit_settings = AlliancePlatformAuditSettings(
    "AUDIT",
    defaults=DEFAULTS,  # type: ignore[has-type]
)
