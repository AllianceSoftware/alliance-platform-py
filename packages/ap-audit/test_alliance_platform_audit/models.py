from common_audit import with_audit_model
from common_audit.registry import AuditRegistry
from django.db import models
from django.db.models import CASCADE

test_audit_registry = AuditRegistry()


@with_audit_model(registry=test_audit_registry)
class PaymentMethod(models.Model):
    name = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "test_common_audit_payment_method"

    def __str__(self):
        return f"{self.name}"


@with_audit_model(
    registry=test_audit_registry,
    manual_events=["STORMED"],
)
class Plaza(models.Model):
    name = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "test_common_audit_plaza"

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
        db_table = "test_common_audit_shop"

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
        db_table = "test_common_audit_profile"


@with_audit_model(
    registry=test_audit_registry,
    related_name="member_events",
    manual_events=["REFER", "TRACK", "BOUNCE"],
)
class MemberProfile(Profile):
    member_id = models.IntegerField()

    class Meta:
        db_table = "test_common_audit_member_profile"


@with_audit_model(
    registry=test_audit_registry,
    related_name="super_member_auditevents",
    manual_events=["REDEEM", "TRACK"],
)
class SuperMemberProfile(MemberProfile):
    award_points = models.IntegerField()

    class Meta:
        db_table = "test_common_audit_super_member_profile"


@with_audit_model(
    registry=test_audit_registry,
    related_name="author_auditevents",
)
class AuthorProfile(Profile):
    homepage = models.URLField()

    class Meta:
        db_table = "test_common_audit_author_profile"
