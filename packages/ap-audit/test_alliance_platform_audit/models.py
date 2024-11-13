from alliance_platform.audit import create_audit_event
from alliance_platform.audit import with_audit_model
from alliance_platform.audit.registry import AuditRegistry
from django.contrib.auth import user_logged_in
from django.contrib.auth import user_logged_out
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import CASCADE
import pghistory

test_audit_registry = AuditRegistry()


@with_audit_model(registry=test_audit_registry)
class PaymentMethod(models.Model):
    name = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "test_alliance_platform_audit_payment_method"

    def __str__(self):
        return f"{self.name}"


@with_audit_model(
    registry=test_audit_registry,
    manual_events=["STORMED"],
)
class Plaza(models.Model):
    name = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "test_alliance_platform_audit_plaza"

    def __str__(self):
        return self.name


class ShopCategory(models.IntegerChoices):
    GROCERY = 1, "Grocery"
    SERVICES = 2, "Services"
    DEPARTMENT = 3, "Department Store"
    OTHER = 0, "Others"


@with_audit_model(registry=test_audit_registry, manual_events=["REVIEW"])
class Shop(models.Model):
    name = models.CharField(max_length=255, blank=True)
    plaza = models.ForeignKey(Plaza, on_delete=CASCADE)
    category = models.PositiveSmallIntegerField(choices=ShopCategory.choices, default=ShopCategory.OTHER)
    payment_methods_accepted = models.ManyToManyField(PaymentMethod, related_name="shops", blank=True)

    class Meta:
        db_table = "test_alliance_platform_audit_shop"

    def __str__(self):
        return f"{self.plaza} - {self.name} ({dict(ShopCategory.choices)[self.category]})"


@with_audit_model(
    registry=test_audit_registry,
    related_name="profile_auditevents",
    manual_events=["LOGIN", "TRACK", "BOUNCE"],
)
class Profile(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        db_table = "test_alliance_platform_audit_profile"


@with_audit_model(
    registry=test_audit_registry,
    related_name="member_events",
    manual_events=["REFER", "TRACK", "BOUNCE"],
)
class MemberProfile(Profile):
    member_id = models.IntegerField()

    class Meta:
        db_table = "test_alliance_platform_audit_member_profile"


@with_audit_model(
    registry=test_audit_registry,
    related_name="super_member_auditevents",
    manual_events=["REDEEM", "TRACK"],
)
class SuperMemberProfile(MemberProfile):
    award_points = models.IntegerField()

    class Meta:
        db_table = "test_alliance_platform_audit_super_member_profile"


@with_audit_model(
    registry=test_audit_registry,
    related_name="author_auditevents",
)
class AuthorProfile(Profile):
    homepage = models.URLField()

    class Meta:
        db_table = "test_alliance_platform_audit_author_profile"


@with_audit_model(
    registry=test_audit_registry,
    related_name="user_auditevent",
    manual_events=["LOGIN"],
)
class User(AbstractUser):
    user_type = "user"

    class Meta:
        db_table = "test_alliance_platform_audit_custom_user"


def track_login(sender, user, **kwargs):
    # Always use the base user
    if hasattr(user, "user_ptr"):
        user = user.user_ptr
    create_audit_event(user, "LOGIN")


def track_logout(sender, user, **kwargs):
    if user:
        # logout is a GET so wont trigger middleware; manually add context here.
        with pghistory.context(user=user.pk):
            # Always use the base user
            if hasattr(user, "user_ptr"):
                user = user.user_ptr
            create_audit_event(user, "LOGOUT")


user_logged_in.connect(track_login)
user_logged_out.connect(track_logout)
