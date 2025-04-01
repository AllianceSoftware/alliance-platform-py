from alliance_platform.ordered_model.models import OrderedModel
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import CASCADE
from django.db.models import QuerySet


class User(AbstractUser):
    class Meta:
        db_table = "test_alliance_platform_ordered_model_custom_user"


class PaymentMethod(models.Model):
    name = models.CharField(max_length=255, blank=True)

    shops: QuerySet["Shop"]

    class Meta:
        db_table = "test_alliance_platform_ordered_model_payment_method"

    def __str__(self):
        return f"{self.name}"


class Plaza(OrderedModel):
    name = models.CharField(max_length=255, blank=True)
    sort_key = models.PositiveIntegerField(blank=True)
    notify_on_reorder = "test_alliance_platform_ordered_model_notifications"

    class Meta:
        db_table = "test_alliance_platform_ordered_model_plaza"
        ordering = ["name"]

    def __str__(self):
        return self.name


class ShopCategory(models.IntegerChoices):
    GROCERY = 1, "Grocery"
    SERVICES = 2, "Services"
    DEPARTMENT = 3, "Department Store"
    OTHER = 0, "Others"


class Shop(OrderedModel):
    name = models.CharField(max_length=255, blank=True)
    plaza = models.ForeignKey(Plaza, on_delete=CASCADE)
    category = models.PositiveSmallIntegerField(choices=ShopCategory.choices, default=ShopCategory.OTHER)
    payment_methods_accepted = models.ManyToManyField(PaymentMethod, related_name="shops", blank=True)
    sort_key = models.PositiveIntegerField(blank=True)

    order_with_respect_to = "plaza"
    notify_on_reorder = "test_alliance_platform_ordered_model_notifications"

    class Meta:
        db_table = "test_alliance_platform_ordered_model_shop"

    def __str__(self):
        return f"{self.plaza} - {self.name} ({dict(ShopCategory.choices)[self.category]})"


class Franchise(models.Model):
    name = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "test_alliance_platform_ordered_model_franchise"

    def __str__(self):
        return f"{self.name}"


class FranchiseLocation(OrderedModel):
    name = models.CharField(max_length=255, blank=True)
    plaza = models.ForeignKey(Plaza, on_delete=CASCADE)
    franchise = models.ForeignKey(Franchise, on_delete=CASCADE)
    sort_key = models.PositiveIntegerField(blank=True)

    order_with_respect_to = ("franchise", "plaza")
    notify_on_reorder = "test_alliance_platform_ordered_model_notifications"

    class Meta:
        db_table = "test_alliance_platform_ordered_model_franchise_location"

    def __str__(self):
        return f"{self.plaza} - {self.franchise}"
