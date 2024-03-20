import rules

from xenopus_frog_app.models import User


def link_is_allowed(user: User, obj: User | None = None) -> bool:
    return user.is_superuser


# We use rules here as it's easier than setting up a custom CSV permissions
rules.add_perm("test_common_frontend.link_is_allowed", link_is_allowed)
