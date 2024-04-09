from allianceutils.auth.models import GenericUserProfile
from allianceutils.auth.models import GenericUserProfileManagerMixin
from allianceutils.auth.permission import NoDefaultPermissionsMeta
import django.contrib.auth.models as auth_models
from django.db import models


class UserManager(GenericUserProfileManagerMixin, auth_models.UserManager):
    def get_by_natural_key(self, username: str | None):
        username = self.normalize_email(username)
        return super().get_by_natural_key(username)


class User(GenericUserProfile, auth_models.AbstractBaseUser, auth_models.PermissionsMixin):
    USERNAME_FIELD = "email"

    email = models.EmailField(db_collation="case_insensitive", unique=True)
    objects = UserManager()  # type:ignore[misc,assignment]  # specialising type
    profiles = UserManager(select_related_profiles=True)  # type: ignore[misc,assignment] # specialising type
    # Used in CSV permission to identify which permissions apply. This should be set on subclasses.
    user_type: str | None = None

    related_profile_tables = ["adminprofile", "customerprofile"]

    # We don't use django.contrib.auth.backends.ModelBackend at all so remove these unused fields:
    groups = None  # type: ignore[assignment]
    user_permissions = None  # type: ignore[assignment]

    class Meta(NoDefaultPermissionsMeta):
        db_table = "test_alliance_platform_frontend_user"


class AdminProfile(User):
    user_type = "admin"

    class Meta:
        db_table = "test_alliance_platform_frontend_adminprofile"


class CustomerProfile(User):
    user_type = "customer"

    class Meta:
        db_table = "test_alliance_platform_frontend_customerprofile"
