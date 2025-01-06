from django.contrib.auth.models import PermissionsMixin
import rules


def link_is_allowed(user: PermissionsMixin, obj: PermissionsMixin | None = None) -> bool:
    return user.is_superuser


# We use rules here as it's easier than setting up a custom CSV permissions
rules.add_perm("test_utils.link_is_allowed", link_is_allowed)
