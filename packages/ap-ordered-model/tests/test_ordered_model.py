import json
from typing import cast

from alliance_platform.ordered_model.models import OrderedModel
from alliance_platform.ordered_model.models import UnexpectedOrderError
from django.db import connections
from django.db import models
from django.test import TransactionTestCase
from test_alliance_platform_ordered_model.factory import AppFranchiseFactory
from test_alliance_platform_ordered_model.factory import AppFranchiseLocationFactory
from test_alliance_platform_ordered_model.factory import AppPlazaFactory
from test_alliance_platform_ordered_model.factory import AppShopFactory
from test_alliance_platform_ordered_model.models import Franchise
from test_alliance_platform_ordered_model.models import FranchiseLocation
from test_alliance_platform_ordered_model.models import Plaza
from test_alliance_platform_ordered_model.models import Shop


class TestOrderedModel(TransactionTestCase):
    def test_ordered(self):
        plaza1 = cast(Plaza, AppPlazaFactory())
        plaza2 = cast(Plaza, AppPlazaFactory())
        plaza1.refresh_from_db()
        plaza2.refresh_from_db()
        self.assertEqual(plaza1.sort_key, 2)
        self.assertEqual(plaza2.sort_key, 4)
        plaza2.sort_key = 1
        plaza2.save(update_fields=["sort_key"])
        self.assertEqual(Plaza.objects.get(pk=plaza1.pk).sort_key, 4)
        self.assertEqual(Plaza.objects.get(pk=plaza2.pk).sort_key, 2)
        # plaza1 will still have old sort_key - a save shouldn't write this
        self.assertEqual(plaza1.sort_key, 2)
        plaza1.save()
        self.assertEqual(Plaza.objects.get(pk=plaza1.pk).sort_key, 4)
        self.assertEqual(Plaza.objects.get(pk=plaza2.pk).sort_key, 2)

    def test_ordered_with_respect_to(self):
        plaza1 = cast(Plaza, AppPlazaFactory())
        plaza2 = cast(Plaza, AppPlazaFactory())

        plaza1_shops = [AppShopFactory(plaza=plaza1, name=f"P1-{i}") for i in range(5)]
        plaza2_shops = [AppShopFactory(plaza=plaza2, name=f"P2-{i}") for i in range(5)]
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P1-1", 4), ("P1-2", 6), ("P1-3", 8), ("P1-4", 10)],
        )
        self.assertEqual(
            list(plaza2.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P2-0", 2), ("P2-1", 4), ("P2-2", 6), ("P2-3", 8), ("P2-4", 10)],
        )
        plaza1_shops[0].sort_key = 9
        plaza1_shops[0].save(update_fields=["sort_key"])
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-1", 2), ("P1-2", 4), ("P1-3", 6), ("P1-0", 8), ("P1-4", 10)],
        )
        self.assertEqual(
            list(plaza2.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P2-0", 2), ("P2-1", 4), ("P2-2", 6), ("P2-3", 8), ("P2-4", 10)],
        )
        plaza2_shops[3].sort_key = 0
        plaza2_shops[3].save(update_fields=["sort_key"])
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-1", 2), ("P1-2", 4), ("P1-3", 6), ("P1-0", 8), ("P1-4", 10)],
        )
        self.assertEqual(
            list(plaza2.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P2-3", 2), ("P2-0", 4), ("P2-1", 6), ("P2-2", 8), ("P2-4", 10)],
        )

    def test_move_between(self):
        plaza1 = cast(Plaza, AppPlazaFactory())
        shops = [AppShopFactory(plaza=plaza1, name=f"P1-{i}") for i in range(5)]
        first_shop = shops[0]
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P1-1", 4), ("P1-2", 6), ("P1-3", 8), ("P1-4", 10)],
        )
        first_shop.refresh_from_db()
        first_shop.move_between(shops[2], shops[3])
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-1", 2), ("P1-2", 4), ("P1-0", 6), ("P1-3", 8), ("P1-4", 10)],
        )
        with self.assertRaises(UnexpectedOrderError):
            shops[0].move_between(shops[2].pk, shops[3].pk)

        first_shop.refresh_from_db()
        first_shop.move_between(shops[-1].pk, None)
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-1", 2), ("P1-2", 4), ("P1-3", 6), ("P1-4", 8), ("P1-0", 10)],
        )

        first_shop.refresh_from_db()
        first_shop.move_between(None, shops[1].pk)
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P1-1", 4), ("P1-2", 6), ("P1-3", 8), ("P1-4", 10)],
        )

        with self.assertRaisesMessage(UnexpectedOrderError, "item order has changed"):
            first_shop.move_between(None, shops[1].pk)

        first_shop.delete()
        with self.assertRaisesMessage(ValueError, "item no longer exists"):
            first_shop.move_between(None, shops[1].pk)

    def test_move_between_with_respect_to(self):
        """Moves a shop between two other shows in a different plaza"""
        plaza1 = cast(Plaza, AppPlazaFactory(name="plaza1"))
        plaza2 = cast(Plaza, AppPlazaFactory(name="plaza2"))
        for i in range(5):
            AppShopFactory(plaza=plaza1, name=f"P1-{i}")
            AppShopFactory(plaza=plaza2, name=f"P2-{i}")
        plaza1_shops = list(plaza1.shop_set.order_by("sort_key"))
        plaza2_shops = list(plaza2.shop_set.order_by("sort_key"))

        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P1-1", 4), ("P1-2", 6), ("P1-3", 8), ("P1-4", 10)],
        )
        self.assertEqual(
            list(plaza2.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P2-0", 2), ("P2-1", 4), ("P2-2", 6), ("P2-3", 8), ("P2-4", 10)],
        )

        with self.assertRaisesMessage(
            UnexpectedOrderError, "are no longer adjacent (different plaza_id values)"
        ):
            plaza1_shops[-1].move_between(plaza1_shops[0], plaza2_shops[1])

        plaza1_shops[-1].move_between(plaza2_shops[0], plaza2_shops[1])
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P1-1", 4), ("P1-2", 6), ("P1-3", 8)],
        )
        self.assertEqual(
            list(plaza2.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P2-0", 2), ("P1-4", 4), ("P2-1", 6), ("P2-2", 8), ("P2-3", 10), ("P2-4", 12)],
        )

        plaza1_shops = list(plaza1.shop_set.all().order_by("sort_key"))
        plaza2_shops = list(plaza2.shop_set.all().order_by("sort_key"))
        plaza2_shops[-1].move_between(plaza1_shops[-1], None)
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P1-1", 4), ("P1-2", 6), ("P1-3", 8), ("P2-4", 10)],
        )
        self.assertEqual(
            list(plaza2.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P2-0", 2), ("P1-4", 4), ("P2-1", 6), ("P2-2", 8), ("P2-3", 10)],
        )

        plaza1_shops = list(plaza1.shop_set.all().order_by("sort_key"))
        plaza2_shops = list(plaza2.shop_set.all().order_by("sort_key"))
        plaza1_shops[0].move_between(None, plaza2_shops[0])
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-1", 2), ("P1-2", 4), ("P1-3", 6), ("P2-4", 8)],
        )
        self.assertEqual(
            list(plaza2.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P2-0", 4), ("P1-4", 6), ("P2-1", 8), ("P2-2", 10), ("P2-3", 12)],
        )

    def test_move_before(self):
        plaza1 = cast(Plaza, AppPlazaFactory())
        shops = [AppShopFactory(plaza=plaza1, name=f"P1-{i}") for i in range(5)]
        first_shop = shops[0]
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P1-1", 4), ("P1-2", 6), ("P1-3", 8), ("P1-4", 10)],
        )
        first_shop.move_before(shops[2].pk)
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-1", 2), ("P1-0", 4), ("P1-2", 6), ("P1-3", 8), ("P1-4", 10)],
        )
        first_shop.move_before(shops[-1].pk)
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-1", 2), ("P1-2", 4), ("P1-3", 6), ("P1-0", 8), ("P1-4", 10)],
        )

    def test_move_after(self):
        plaza1 = cast(Plaza, AppPlazaFactory())
        shops = [AppShopFactory(plaza=plaza1, name=f"P1-{i}") for i in range(5)]
        first_shop = shops[0]
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P1-1", 4), ("P1-2", 6), ("P1-3", 8), ("P1-4", 10)],
        )
        first_shop.move_after(shops[2].pk)
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-1", 2), ("P1-2", 4), ("P1-0", 6), ("P1-3", 8), ("P1-4", 10)],
        )
        first_shop.move_after(shops[-1].pk)
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-1", 2), ("P1-2", 4), ("P1-3", 6), ("P1-4", 8), ("P1-0", 10)],
        )

    def test_move_start(self):
        plaza1 = cast(Plaza, AppPlazaFactory())
        shops = [AppShopFactory(plaza=plaza1, name=f"P1-{i}") for i in range(5)]
        last_shop = shops[-1]
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P1-1", 4), ("P1-2", 6), ("P1-3", 8), ("P1-4", 10)],
        )
        last_shop.move_start()
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-4", 2), ("P1-0", 4), ("P1-1", 6), ("P1-2", 8), ("P1-3", 10)],
        )

    def test_move_end(self):
        plaza1 = cast(Plaza, AppPlazaFactory())
        shops = [AppShopFactory(plaza=plaza1, name=f"P1-{i}") for i in range(5)]
        first_shop = shops[0]
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P1-1", 4), ("P1-2", 6), ("P1-3", 8), ("P1-4", 10)],
        )
        first_shop.move_end()
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-1", 2), ("P1-2", 4), ("P1-3", 6), ("P1-4", 8), ("P1-0", 10)],
        )

    def test_change_with_respect_to(self):
        plaza1 = cast(Plaza, AppPlazaFactory())
        plaza1_shops = [AppShopFactory(plaza=plaza1, name=f"P1-{i}") for i in range(5)]
        plaza2 = cast(Plaza, AppPlazaFactory())
        for i in range(5):
            AppShopFactory(plaza=plaza2, name=f"P2-{i}")
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P1-1", 4), ("P1-2", 6), ("P1-3", 8), ("P1-4", 10)],
        )
        self.assertEqual(
            list(plaza2.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P2-0", 2), ("P2-1", 4), ("P2-2", 6), ("P2-3", 8), ("P2-4", 10)],
        )
        plaza1_shops[0].plaza = plaza2
        plaza1_shops[0].sort_key = 0
        plaza1_shops[0].save(update_fields=["plaza", "sort_key"])
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-1", 2), ("P1-2", 4), ("P1-3", 6), ("P1-4", 8)],
        )
        self.assertEqual(
            list(plaza2.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P2-0", 4), ("P2-1", 6), ("P2-2", 8), ("P2-3", 10), ("P2-4", 12)],
        )

    def test_bulk_update(self):
        for batch_size in [2, None]:
            with self.subTest(f"bulk_update batch_sized={batch_size}"):
                plaza1 = cast(Plaza, AppPlazaFactory())
                plaza1_shops = [AppShopFactory(plaza=plaza1, name=f"P1-{i}") for i in range(5)]
                plaza2 = cast(Plaza, AppPlazaFactory())
                plaza2_shops = [AppShopFactory(plaza=plaza2, name=f"P2-{i}") for i in range(5)]
                self.assertEqual(
                    list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
                    [("P1-0", 2), ("P1-1", 4), ("P1-2", 6), ("P1-3", 8), ("P1-4", 10)],
                )
                for i, obj in enumerate(reversed(plaza1_shops)):
                    obj.sort_key = i + 100
                for i, obj in enumerate(reversed(plaza2_shops)):
                    obj.sort_key = i + 100
                with connections["default"].cursor() as curs:
                    conn = curs.connection
                    notifications = []

                    def notify_handler(n):
                        notifications.append(n)

                    conn.add_notify_handler(notify_handler)
                    curs.execute("LISTEN test_alliance_platform_ordered_model_notifications;")
                    if batch_size is None:
                        Shop.objects.bulk_update(plaza1_shops + plaza2_shops, ["sort_key"])
                    else:
                        # With batch_size != None need to defer triggers and apply update once at end
                        with Shop.defer_triggers():
                            Shop.objects.bulk_update(
                                plaza1_shops + plaza2_shops, ["sort_key"], batch_size=batch_size
                            )
                    self.assertEqual(
                        list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
                        [("P1-4", 2), ("P1-3", 4), ("P1-2", 6), ("P1-1", 8), ("P1-0", 10)],
                    )
                    self.assertEqual(
                        list(plaza2.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
                        [("P2-4", 2), ("P2-3", 4), ("P2-2", 6), ("P2-1", 8), ("P2-0", 10)],
                    )
                    self.assertEqual(len(notifications), 2)
                    notification = notifications.pop(0)
                    payload = json.loads(notification.payload)
                    self.assertEqual(payload["operation"], "UPDATE")
                    self.assertEqual(payload["table"], Shop._meta.db_table)
                    self.assertEqual(
                        payload["order_with_respect_to"],
                        {"plaza": plaza1.pk},
                    )
                    notification = notifications.pop(0)
                    payload = json.loads(notification.payload)
                    self.assertEqual(payload["operation"], "UPDATE")
                    self.assertEqual(payload["table"], Shop._meta.db_table)
                    self.assertEqual(
                        payload["order_with_respect_to"],
                        {"plaza": plaza2.pk},
                    )
                    self.assertFalse(notifications)
                    plaza1_shops[0].save()
                    self.assertFalse(notifications)
                    conn.remove_notify_handler(notify_handler)
                    curs.execute("UNLISTEN test_alliance_platform_ordered_model_notifications;")

    def test_validate_unique_constraint(self):
        with self.assertRaisesMessage(ValueError, "sort_key should not have a unique constraint"):

            class TestOrderedModel1(OrderedModel):
                sort_key = models.IntegerField(unique=True)

                class Meta:
                    app_label = "test_alliance_platform_ordered_model"

        with self.assertRaisesMessage(ValueError, "sort_key should not have a unique constraint"):

            class TestOrderedModel2(OrderedModel):
                order_with_respect_to = ("column1", "column2")
                column1 = models.IntegerField()
                column2 = models.IntegerField()
                sort_key = models.IntegerField()

                class Meta:
                    unique_together = ("column1", "column2", "sort_key")
                    app_label = "test_alliance_platform_ordered_model"

    def test_notifications(self):
        with connections["default"].cursor() as curs:
            conn = curs.connection
            notifications = []

            def notify_handler(n):
                notifications.append(n)

            conn.add_notify_handler(notify_handler)
            curs.execute("LISTEN test_alliance_platform_ordered_model_notifications;")
            plaza = AppPlazaFactory()
            shop1 = AppShopFactory(plaza=plaza)
            self.assertTrue(notifications)
            notification = notifications.pop(0)
            payload = json.loads(notification.payload)
            self.assertEqual(
                list(payload.keys()),
                [
                    "timestamp",
                    "notification_type",
                    "operation",
                    "schema",
                    "table",
                    "originator_id",
                    "order_with_respect_to",
                ],
            )
            self.assertEqual(payload["operation"], "INSERT")
            self.assertEqual(payload["table"], Plaza._meta.db_table)
            self.assertEqual(
                payload["order_with_respect_to"],
                None,
            )
            notification = notifications.pop(0)
            payload = json.loads(notification.payload)
            self.assertEqual(payload["operation"], "INSERT")
            self.assertEqual(payload["table"], Shop._meta.db_table)
            self.assertEqual(
                payload["order_with_respect_to"],
                {"plaza": plaza.pk},
            )
            shop2 = AppShopFactory(plaza=plaza)
            notifications.pop(0)
            shop2.sort_key = 0
            shop2.save(update_fields=["sort_key"])
            notification = notifications.pop(0)
            payload = json.loads(notification.payload)
            self.assertEqual(payload["operation"], "UPDATE")
            self.assertEqual(payload["table"], Shop._meta.db_table)
            self.assertEqual(
                payload["order_with_respect_to"],
                {"plaza": plaza.pk},
            )
            plaza.sort_key = 0
            plaza.save(update_fields=["sort_key"])
            notification = notifications.pop(0)
            payload = json.loads(notification.payload)
            self.assertEqual(payload["operation"], "UPDATE")
            self.assertEqual(payload["table"], plaza._meta.db_table)
            self.assertEqual(
                payload["order_with_respect_to"],
                None,
            )
            self.assertFalse(notifications)

            # Don't fire notifications if nothing has changed
            shop2.refresh_from_db()
            shop2.save(update_fields=["sort_key"])
            self.assertFalse(notifications)

            plaza.refresh_from_db()
            plaza.save(update_fields=["sort_key"])
            self.assertFalse(notifications)

            # Moving to a different plaza should trigger 2 notifications - one for old plaza & one for new
            plaza2 = AppPlazaFactory()
            notification = notifications.pop(0)
            payload = json.loads(notification.payload)
            self.assertEqual(payload["operation"], "INSERT")
            self.assertEqual(payload["table"], Plaza._meta.db_table)
            shop2.plaza = plaza2
            shop2.save()
            self.assertEqual(len(notifications), 2)
            notification = notifications.pop(0)
            payload = json.loads(notification.payload)
            self.assertEqual(payload["operation"], "UPDATE")
            self.assertEqual(payload["table"], Shop._meta.db_table)
            self.assertEqual(
                payload["order_with_respect_to"],
                {"plaza": plaza.pk},
            )
            notification = notifications.pop(0)
            payload = json.loads(notification.payload)
            self.assertEqual(payload["operation"], "UPDATE")
            self.assertEqual(payload["table"], Shop._meta.db_table)
            self.assertEqual(
                payload["order_with_respect_to"],
                {"plaza": plaza2.pk},
            )

            # Should trigger on queryset bulk changes too
            plaza2.shop_set.all().move_between(shop1, None)
            self.assertEqual(len(notifications), 2)

            notification = notifications.pop(0)
            payload = json.loads(notification.payload)
            self.assertEqual(payload["operation"], "UPDATE")
            self.assertEqual(payload["table"], Shop._meta.db_table)
            self.assertEqual(
                payload["order_with_respect_to"],
                {"plaza": plaza2.pk},
            )
            notification = notifications.pop(0)
            payload = json.loads(notification.payload)
            self.assertEqual(payload["operation"], "UPDATE")
            self.assertEqual(payload["table"], Shop._meta.db_table)
            self.assertEqual(
                payload["order_with_respect_to"],
                {"plaza": plaza.pk},
            )

    def test_defer_triggers(self):
        plaza1 = cast(Plaza, AppPlazaFactory())
        plaza1_shops = [AppShopFactory(plaza=plaza1, name=f"P1-{i}") for i in range(5)]
        plaza2 = cast(Plaza, AppPlazaFactory())
        for i in range(5):
            AppShopFactory(plaza=plaza2, name=f"P2-{i}")
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P1-1", 4), ("P1-2", 6), ("P1-3", 8), ("P1-4", 10)],
        )
        self.assertEqual(
            list(plaza2.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P2-0", 2), ("P2-1", 4), ("P2-2", 6), ("P2-3", 8), ("P2-4", 10)],
        )

        with connections["default"].cursor() as curs:
            conn = curs.connection
            notifications = []

            def notify_handler(n):
                notifications.append(n)

            conn.add_notify_handler(notify_handler)
            curs.execute("LISTEN test_alliance_platform_ordered_model_notifications;")

            with Shop.defer_triggers():
                for i, shop in enumerate(reversed(plaza1_shops)):
                    shop.sort_key = i
                    shop.save(update_fields=["sort_key"])
            self.assertEqual(
                list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
                [("P1-4", 2), ("P1-3", 4), ("P1-2", 6), ("P1-1", 8), ("P1-0", 10)],
            )
            self.assertEqual(
                list(plaza2.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
                [("P2-0", 2), ("P2-1", 4), ("P2-2", 6), ("P2-3", 8), ("P2-4", 10)],
            )
            self.assertEqual(len(notifications), 2)
            notification = notifications.pop(0)
            payload = json.loads(notification.payload)
            self.assertEqual(payload["operation"], "UPDATE")
            self.assertEqual(payload["table"], Shop._meta.db_table)
            self.assertEqual(
                payload["order_with_respect_to"],
                {"plaza": plaza1.pk},
            )

            # We get notification for plaza2 even though nothing changed
            notification = notifications.pop(0)
            payload = json.loads(notification.payload)
            self.assertEqual(payload["operation"], "UPDATE")
            self.assertEqual(payload["table"], Shop._meta.db_table)
            self.assertEqual(
                payload["order_with_respect_to"],
                {"plaza": plaza2.pk},
            )

    def test_queryset_move_between(self):
        plaza1 = cast(Plaza, AppPlazaFactory())
        shops = [AppShopFactory(plaza=plaza1, name=f"P1-{i}") for i in range(5)]
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P1-1", 4), ("P1-2", 6), ("P1-3", 8), ("P1-4", 10)],
        )
        plaza1.shop_set.filter(sort_key__lte=6).move_between(shops[3], shops[4])
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-3", 2), ("P1-0", 4), ("P1-1", 6), ("P1-2", 8), ("P1-4", 10)],
        )

        # Move to start of list
        plaza1.shop_set.filter(name__in=("P1-4", "P1-1")).move_between(
            None, plaza1.shop_set.order_by("sort_key").first()
        )
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-1", 2), ("P1-4", 4), ("P1-3", 6), ("P1-0", 8), ("P1-2", 10)],
        )

        # Move to end of list
        last = plaza1.shop_set.order_by("sort_key").last()
        plaza1.shop_set.filter(name__in=("P1-0", "P1-4")).move_between(last, None)
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-1", 2), ("P1-3", 4), ("P1-2", 6), ("P1-4", 8), ("P1-0", 10)],
        )

        # These moves P1-0 and P1-2 to between P1-3 and P1-4 - which is where P1-2 already is
        # This shouldn't raise the 'no longer adjacent' error as we consider them adjacent if
        # we exclude the items being moved
        item_3 = plaza1.shop_set.get(name="P1-3")
        item_4 = plaza1.shop_set.get(name="P1-4")
        plaza1.shop_set.filter(name__in=("P1-0", "P1-2")).move_between(item_3, item_4)
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-1", 2), ("P1-3", 4), ("P1-2", 6), ("P1-0", 8), ("P1-4", 10)],
        )

        with self.assertRaisesMessage(UnexpectedOrderError, "are no longer adjacent"):
            item_1 = plaza1.shop_set.get(name="P1-1")
            item_2 = plaza1.shop_set.get(name="P1-2")
            plaza1.shop_set.filter(name__in=("P1-0", "P1-4")).move_between(item_1, item_2)

        with self.assertRaisesMessage(UnexpectedOrderError, "no longer at the end of the list"):
            # P1-0 isn't last so should error
            plaza1.shop_set.filter(name__in=("P1-1", "P1-3")).move_between(
                plaza1.shop_set.get(name="P1-0"), None
            )

        item_0 = plaza1.shop_set.get(name="P1-0")
        item_0_pk = item_0.pk
        item_0.delete()
        with self.assertRaisesMessage(UnexpectedOrderError, "records not found"):
            plaza1.shop_set.filter(name__in=("P1-1", "P1-4")).move_between(item_0_pk, None)

    def test_queryset_move_between_with_respect_to(self):
        """Moves multiple shops between plazas"""
        plaza1 = cast(Plaza, AppPlazaFactory())
        plaza2 = cast(Plaza, AppPlazaFactory())
        plaza1_shops = [AppShopFactory(plaza=plaza1, name=f"P1-{i}") for i in range(5)]
        plaza2_shops = [AppShopFactory(plaza=plaza2, name=f"P2-{i}") for i in range(5)]

        with self.assertRaisesMessage(
            UnexpectedOrderError, "are no longer adjacent (different plaza_id values)"
        ):
            plaza1.shop_set.filter(name__in=("P1-1", "P1-4")).move_between(plaza1_shops[0], plaza2_shops[1])

            with self.assertRaisesMessage(UnexpectedOrderError, "are no longer adjacent"):
                plaza1.shop_set.filter(name__in=("P1-1", "P1-4")).move_between(
                    plaza2_shops[0], plaza2_shops[2]
                )

        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P1-1", 4), ("P1-2", 6), ("P1-3", 8), ("P1-4", 10)],
        )
        self.assertEqual(
            list(plaza2.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P2-0", 2), ("P2-1", 4), ("P2-2", 6), ("P2-3", 8), ("P2-4", 10)],
        )

        plaza1.shop_set.filter(name__in=("P1-4", "P1-1")).move_between(plaza2_shops[0], plaza2_shops[1])
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P1-2", 4), ("P1-3", 6)],
        )
        self.assertEqual(
            list(plaza2.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P2-0", 2), ("P1-1", 4), ("P1-4", 6), ("P2-1", 8), ("P2-2", 10), ("P2-3", 12), ("P2-4", 14)],
        )

        # move to end
        plaza1_shops = list(plaza1.shop_set.all().order_by("sort_key"))
        plaza2.shop_set.filter(name__in=("P1-4", "P1-1")).move_between(plaza1_shops[-1], None)
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P1-2", 4), ("P1-3", 6), ("P1-1", 8), ("P1-4", 10)],
        )
        self.assertEqual(
            list(plaza2.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P2-0", 2), ("P2-1", 4), ("P2-2", 6), ("P2-3", 8), ("P2-4", 10)],
        )

        # move to start
        plaza2_shops = list(plaza2.shop_set.all().order_by("sort_key"))
        plaza1.shop_set.filter(name__in=("P1-4", "P1-1")).move_between(None, plaza2_shops[0])
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-0", 2), ("P1-2", 4), ("P1-3", 6)],
        )
        self.assertEqual(
            list(plaza2.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-1", 2), ("P1-4", 4), ("P2-0", 6), ("P2-1", 8), ("P2-2", 10), ("P2-3", 12), ("P2-4", 14)],
        )

        plaza1_shops = list(plaza1.shop_set.all().order_by("sort_key"))
        plaza2.shop_set.filter(name="P1-1").move_between(None, plaza1_shops[0])
        self.assertEqual(
            list(plaza1.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-1", 2), ("P1-0", 4), ("P1-2", 6), ("P1-3", 8)],
        )
        self.assertEqual(
            list(plaza2.shop_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [("P1-4", 2), ("P2-0", 4), ("P2-1", 6), ("P2-2", 8), ("P2-3", 10), ("P2-4", 12)],
        )

    def test_multiple_order_with_respect_to(self):
        plaza1 = cast(Plaza, AppPlazaFactory())
        plaza2 = cast(Plaza, AppPlazaFactory())

        franchise1 = cast(Franchise, AppFranchiseFactory())
        franchise2 = cast(Franchise, AppFranchiseFactory())

        plaza_1_franchise_1_locations = [
            AppFranchiseLocationFactory(plaza=plaza1, franchise=franchise1, name=f"p1-f1-{i}")
            for i in range(3)
        ]

        for i in range(3):
            AppFranchiseLocationFactory(plaza=plaza2, franchise=franchise1, name=f"p2-f1-{i}")
            AppFranchiseLocationFactory(plaza=plaza1, franchise=franchise2, name=f"p1-f2-{i}")
            AppFranchiseLocationFactory(plaza=plaza2, franchise=franchise2, name=f"p2-f2-{i}")

        self.assertEqual(
            list(plaza1.franchiselocation_set.all().order_by("sort_key").values_list("name", "sort_key")),
            [
                ("p1-f1-0", 2),
                ("p1-f2-0", 2),
                ("p1-f1-1", 4),
                ("p1-f2-1", 4),
                ("p1-f1-2", 6),
                ("p1-f2-2", 6),
            ],
        )

        plaza_1_franchise_1_filter = cast(
            FranchiseLocation, plaza_1_franchise_1_locations[0]
        )._get_order_with_respect_to_filter()
        self.assertEqual(
            plaza_1_franchise_1_locations, list(FranchiseLocation.objects.filter(plaza_1_franchise_1_filter))
        )
