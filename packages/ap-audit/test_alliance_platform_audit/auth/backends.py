from alliance_platform.audit.settings import ap_audit_settings
from django.contrib.auth.backends import ModelBackend

permissions = {
    "test_alliance_platform_audit.shop_audit": True,
    "test_alliance_platform_audit.plaza_audit": False,
}


# mock as false to disable
def global_audit_enabled():
    return True


def can_hijack(*args, **kwargs):
    return True


class AuditBackend(ModelBackend):
    def has_audit_perm(self, perm):
        if (has_perm := permissions.get(perm)) is not None:
            return has_perm
        return False

    def has_perm(self, user_obj, perm: str, obj=None):
        if perm == ap_audit_settings.GLOBAL_AUDIT_PERMISSION_NAME:
            return global_audit_enabled()
        if perm.endswith("audit"):
            return self.has_audit_perm(perm)

        return super().has_perm(user_obj, perm, obj=obj)
