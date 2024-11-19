from typing import TypedDict

from alliance_platform.base_settings import AlliancePlatformSettingsBase
from django.db.models import Value
from django.db.models.expressions import Func
from django.db.models.functions import Concat


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

    #: The name of the action used to evaluate permissions for auditing a model. Defaults to 'audit'.
    LIST_PERM_ACTION: str | None
    #: The name of the permission used to evaluate whether auditing of any type can be performed. If it resolves to ``False``,
    #: this will override individual audit permissions determined by ``LIST_PERM_ACTION``. Defaults to
    #: ``"alliance_platform.audit.can_audit"``
    GLOBAL_AUDIT_PERMISSION_NAME: str | None
    #: The SQL function used to generate the display name for users in audit logs. Defaults to showing first name and last name
    USERNAME_FORMAT: Func | None
    #: The format string to use when displaying timestamps for audit logs. Defaults to ``"%Y-%m-%d %H:%M:%S"``
    DATETIME_FORMAT: str | None
    #: Whether to include IP address in context logs. make sure you take GDPR into consideration (recording without disclosure
    #: is a violation; ie. minimal: your site need to have a privacy statement somewhere.). Defaults to ``False``.
    TRACK_IP_ADDRESS: bool | None
    #: Path to frontend component for rendering audit log component. Defaults to ``"@alliancesoftware/ui-audit/AuditLog"``. Accepts
    #: ``.ts``, ``.tsx``, and ``.jsx`` extensions.
    AUDIT_LOG_COMPONENT_PATH: str | None


class AlliancePlatformAuditSettings(AlliancePlatformSettingsBase):
    #: The name of the action used to evaluate permissions for auditing a model. Defaults to 'audit'.
    LIST_PERM_ACTION: str
    #: The name of the permission used to evaluate whether auditing of any type can be performed. If it resolves to ``False``,
    #: this will override individual audit permissions determined by ``LIST_PERM_ACTION``. Defaults to
    #: ``"alliance_platform.audit.can_audit"``
    GLOBAL_AUDIT_PERMISSION_NAME: str
    #: The SQL function used to generate the display name for users in audit logs. Defaults to showing first name and last name
    USERNAME_FORMAT: Func
    #: The format string to use when displaying timestamps for audit logs. Defaults to '%Y-%m-%d %H:%M:%S'
    DATETIME_FORMAT: str
    #: Whether to include IP address in context logs. make sure you take GDPR into consideration (recording without disclosure
    #: is a violation; ie. minimal: your site need to have a privacy statement somewhere.). Defaults to ``False``.
    TRACK_IP_ADDRESS: bool
    #: Path to frontend component for rendering audit log component. Defaults to ``"@alliancesoftware/ui-audit/AuditLog"``. Accepts
    #: ``.ts``, ``.tsx``, and ``.jsx`` extensions.
    AUDIT_LOG_COMPONENT_PATH: str


DEFAULTS = {
    "LIST_PERM_ACTION": "audit",
    "GLOBAL_AUDIT_PERMISSION_NAME": "alliance_platform_audit.can_audit",
    "USERNAME_FORMAT": Concat("first_name", Value(" "), "last_name"),
    "DATETIME_FORMAT": "%Y-%m-%d %H:%M:%S",
    "TRACK_IP_ADDRESS": False,
    "AUDIT_LOG_COMPONENT_PATH": "@allianceplatform/ui-audit/AuditLog",
}
ap_audit_settings = AlliancePlatformAuditSettings(
    "AUDIT",
    defaults=DEFAULTS,
)
