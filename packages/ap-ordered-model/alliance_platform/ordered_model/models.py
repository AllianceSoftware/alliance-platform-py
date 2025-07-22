from __future__ import annotations

from contextlib import contextmanager
from typing import TypeAlias
from typing import cast

from alliance_platform.ordered_model.triggers import generate_model_trigger_name
from django.core.exceptions import FieldDoesNotExist
from django.db import connection
from django.db import models
from django.db import transaction
from django.db.models import Field
from django.db.models import Q
from django.db.models import Subquery
from django.db.models import Value
from django.db.models.base import ModelBase
import pgtrigger


class OrderedModelMetaClass(ModelBase):
    def __new__(mcs, name, bases, attrs):
        new_class = cast(type["OrderedModel"], super().__new__(mcs, name, bases, attrs))
        meta = new_class._meta
        if meta.abstract:
            return new_class
        table_name = meta.db_table
        assert meta.pk is not None
        pk_name = meta.pk.name
        order_field_name = new_class.order_field_name
        order_with_respect_to = new_class.order_with_respect_to
        if isinstance(order_with_respect_to, str):
            order_with_respect_to = (order_with_respect_to,)
        try:
            field = meta.get_field(order_field_name)
            assert isinstance(field, Field)
            if field.unique:
                raise ValueError(
                    f"{order_field_name} should not have a unique constraint - OrderedModel will guarantee it is always unique"
                )
        except FieldDoesNotExist:
            raise ValueError(
                f"{new_class.__name__} has no field named '{order_field_name}'. Either add this field or set 'order_field_name' to the name of the field used for sorting."
            )
        for unique_constraint in meta.unique_together:
            if order_field_name in unique_constraint:
                raise ValueError(
                    f"{order_field_name} should not have a unique constraint - OrderedModel will guarantee it is always unique"
                )
        # Underlying fields for the specified field names. This is necessary to get the column name which may differ
        # from the field name (eg. `phase` vs `phase_id`)
        order_with_respect_to_fields: list[models.Field] = []
        if order_with_respect_to:
            for field_name in order_with_respect_to:
                field = meta.get_field(field_name)
                assert isinstance(field, Field)
                try:
                    order_with_respect_to_fields.append(field)
                except FieldDoesNotExist:
                    raise ValueError(
                        f"{new_class.__name__} has no field named '{field_name}' but was specified in `order_with_respect_to`."
                    )
        setattr(new_class, "_order_with_respect_to_fields", order_with_respect_to_fields)

        if order_with_respect_to:
            order_with_respect_to_comparisons = []
            columns = []
            order_columns = []
            for f in order_with_respect_to_fields:
                order_with_respect_to_comparisons.append(
                    f"old_values.{f.column} IS DISTINCT FROM new_values.{f.column}"
                )
                columns.append(f"new_values.{f.column}")
                # We need access to the old value if it has changed - we access this by passing `prefix` to the `_generate_*`
                # methods (see below)
                columns.append(f"old_values.{f.column} AS old_{f.column}")
                order_columns.append(f"new_values.{f.column}")
            # This is used to send notification & apply trigger
            # updates to the previous order_with_respect_to_values. Without this changing the grouping would
            # a) not reorder the source grouping so you could have unexpected gaps or b) miss out on notifications
            # that the source grouping changed
            columns.append(
                " OR ".join(order_with_respect_to_comparisons) + " AS _has_order_with_respect_to_changed"
            )
            trigger_update = f"""
                declare
                    row record;
                begin
                    -- for all distinct values for order_with_respect that have some records where
                    -- the order_field_name has changed run the update and send any notifications
                    for row in SELECT DISTINCT {", ".join(columns)}
                               FROM new_values
                             INNER JOIN old_values ON new_values."{pk_name}" = old_values."{pk_name}"
                             -- if nothing has changed don't do anything
                             WHERE
                                -- ordering key changed
                                old_values."{order_field_name}" IS DISTINCT FROM new_values."{order_field_name}"
                                -- or one of the order_with_respect_to values changed
                                OR {" OR ".join(order_with_respect_to_comparisons)}
                             -- order by for consistency in notification order
                             ORDER BY {", ".join(order_columns)}
                        loop
                        -- Items have moved from one grouping to another - this updates & runs notifications for the _old_ grouping
                        IF row._has_order_with_respect_to_changed THEN
                            {new_class._generate_update_query(new_class._get_order_with_respect_to_where_sql("row", prefix="old_"))}
                            {new_class._generate_notify_code("row", prefix="old_")}
                        END IF;
                        {new_class._generate_update_query(new_class._get_order_with_respect_to_where_sql("row"))}
                        {new_class._generate_notify_code("row")}
                        end loop;
                end;
            """
        else:
            trigger_update = f"""
                IF (SELECT COUNT(*) FROM new_values
                    INNER JOIN old_values ON new_values."{pk_name}" = old_values."{pk_name}"
                    WHERE old_values."{order_field_name}" IS DISTINCT FROM new_values."{order_field_name}")
                THEN
                    {new_class._generate_update_query()}
                    {new_class._generate_notify_code()}
                END IF;
            """
        triggers = [
            pgtrigger.Trigger(
                name=generate_model_trigger_name(new_class, "insert_sort_key"),
                operation=pgtrigger.Insert,
                when=pgtrigger.Before,
                condition=pgtrigger.Condition(f'NEW."{order_field_name}" IS NULL'),
                func=f"""
                    NEW.{order_field_name} = (SELECT COALESCE(max("{order_field_name}"), 0) + 2 FROM {table_name} {new_class._get_order_with_respect_to_where_sql("NEW")});
                    {new_class._generate_notify_code("NEW")}
                    RETURN NEW;
                """,
            ),
            pgtrigger.Trigger(
                name=generate_model_trigger_name(new_class, "update_sort_key"),
                level=pgtrigger.Statement,
                operation=pgtrigger.Update,
                referencing=pgtrigger.Referencing(old="old_values", new="new_values"),
                when=pgtrigger.After,
                func=f"""
                 -- This setting is used to prevent recursion; we don't want the trigger to run again due to an update within the triggger
                 IF current_setting('x.' || TG_NAME, true) = '1' THEN
                  RETURN NULL;
                 END IF;
                 PERFORM set_config('x.' || TG_NAME, '1', true);
                 {trigger_update}
                 PERFORM set_config('x.' || TG_NAME, '', true);
                 RETURN NULL;
                """,
            ),
        ]
        new_class._trigger_uris = [trigger.get_uri(new_class) for trigger in triggers]

        pgtrigger.register(*triggers)(new_class)
        return new_class


PkOrModel: TypeAlias = models.Model | str | int


class UnexpectedOrderError(Exception):
    """Thrown when calling `move_between` and items are not in the expected order"""

    pass


class OrderedModelQuerySet(models.QuerySet):
    def move_between(self, before: PkOrModel, after: PkOrModel):
        """Move all items in queryset to between :code:`before` and :code:`after_pk`.

        Raises an error if :code:`before` and :code:`after` are no longer adjacent (eg. something else moved them).
        """
        before_pk = before.pk if isinstance(before, models.Model) else before
        after_pk = after.pk if isinstance(after, models.Model) else after
        qs = self.model._default_manager.filter(pk__in=[before_pk, after_pk]).select_for_update()
        order_field_name = self.model.order_field_name
        pk_name = self.model._meta.pk.name
        ids = list(self.order_by(order_field_name).values_list(pk_name, flat=True))
        if not after and not before:
            raise ValueError("One or both of `before` and `after` must be provided")
        if after_pk is not None and after_pk in ids or before_pk is not None and before_pk in ids:
            raise ValueError("Cannot move an item relative to itself")
        with transaction.atomic():
            first = None
            second = None
            for item in qs:
                if before_pk == item.pk:
                    first = item
                elif after_pk == item.pk:
                    second = item

            if before_pk and not first or after_pk and not second:
                raise UnexpectedOrderError("before_pk / after_pk records not found")
            ordered_items = self.model._default_manager.exclude(pk__in=ids)
            if self.model.order_with_respect_to:
                first_or_second = first or second
                assert first_or_second is not None
                ordered_items = ordered_items.filter(first_or_second._get_order_with_respect_to_filter())
            # This is the ordered position of each item _excluding_ the items being moved. This lets us
            # easily check if to items are considered adjacent.
            position_by_pk = {item.pk: i for i, item in enumerate(ordered_items.order_by(order_field_name))}
            if first and second and self.model.order_with_respect_to:
                for field in self.model._order_with_respect_to_fields:
                    if getattr(first, field.column) != getattr(second, field.column):
                        raise UnexpectedOrderError(
                            f"Items {before_pk} and {after_pk} are no longer adjacent (different {field.column} values); aborting move"
                        )
            if after_pk is None:
                assert first is not None
                if position_by_pk[first.pk] + 1 != len(position_by_pk):
                    raise UnexpectedOrderError(f"Item {before_pk} is no longer at the end of the list")
                lowest_order_value = getattr(first, order_field_name)
                target_order = lowest_order_value + 1
            elif before_pk is None:
                assert second is not None
                if position_by_pk[second.pk] != 0:
                    raise UnexpectedOrderError(f"Item {after_pk} is no longer at the start of the list")
                target_order = 0
                lowest_order_value = 0
            else:
                assert first is not None
                assert second is not None
                if (position_by_pk[second.pk] - position_by_pk[first.pk]) != 1:
                    raise UnexpectedOrderError(
                        f"Items {before_pk} and {after_pk} are no longer adjacent; aborting move"
                    )
                lowest_order_value = getattr(first, order_field_name)
                target_order = lowest_order_value + 1
            filters = [f'"{order_field_name}" > {lowest_order_value}']
            values_to_set = [f'"{order_field_name}" = t.rn']
            if self.model.order_with_respect_to:
                # Need to also set the order_with_respect_to values
                for field in self.model._order_with_respect_to_fields:
                    v = f'"{field.column}" = {getattr(first or second, field.column)}'
                    filters.append(v)
                    values_to_set.append(v)
            with connection.cursor() as cursor:
                # This isn't possible to do with the ORM as you can't doa ` UPDATE .. SET .. FROM `
                cursor.execute(
                    f"""
                    UPDATE {self.model._meta.db_table} SET {", ".join(values_to_set)} FROM
                        (SELECT
                            {pk_name},
                            (row_number() OVER
                                -- if id is in ids then it will have a lower position than any id not in ids and so will come first
                                (ORDER BY array_position(
                                    '{{{",".join(map(str, ids))}}}',
                                   "{pk_name}"
                                ), "{order_field_name}")
                                -- set the new order to the target. Note that this applies to _all_ entries after
                                -- the `lowest_order_value` to properly offset everything (see `filters`)
                                + {target_order}
                            ) as rn FROM {self.model._meta.db_table}
                            WHERE
                            -- select all records that are being moved
                            "{pk_name}" in ({",".join(map(str, ids))})
                            -- as well as anything else in the same 'grouping' (when using order_with_respect_to) and
                            -- that appears after `lowest_order_value`
                            OR ({" AND ".join(filters)})
                        ) t
                        WHERE t."{pk_name}" = {self.model._meta.db_table}."{pk_name}"
                   """
                )


class OrderedModelManager(models.Manager.from_queryset(OrderedModelQuerySet)):  # type: ignore[misc]
    pass


class OrderedModel(models.Model, metaclass=OrderedModelMetaClass):
    """OrderedModel will maintain the ordering field for you using database triggers.

    .. warning:: As this uses database triggers only postgres is supported

    .. warning:: Don't add a unique constraint to the :code:`order_field_name` (or :code:`unique_together` when using
        :code:`order_with_respect_to`) - :code:`OrderedModel` will guarantee uniqueness for you. This is a technical
        limitation due to how the triggers are implemented.

    Guarantees that all records will have a unique value for :code:`order_field_name` with respect to
    :code:`order_with_respect_to` (if specified). Whenever the :code:`order_field_name` changes on a record
    all records will be updated as necessary to guarantee their :code:`order_field_name` is :code:`2` away
    from each other. For example if you have 4 records then the ordering values will be :code:`[2, 4, 6, 8]`.

    This structure allows easy re-ordering by assigning an odd number to :code:`order_field_name`. eg. To
    move the first item between the second last and last it would be assigned to :code:`7`.

    If a new record is created without an explicit ordering field value then it will be given the
    last current ordering value + 2 (ie. added to the end).

    For example :code:`Phase` is sorted on the :code:`sort_key` column with respect to :code:`board`.

    .. code-block:: python

        class Phase(OrderedModel):
            board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="phases")
            title = models.CharField(max_length=255)
            sort_key = models.PositiveIntegerField(blank=True)

            order_field_name = "sort_key"
            order_with_respect_to = ("board", )

    To move a record to a new position with strict checks use :meth:`~common_lib.ordered.move_between`.
    This will validate that the relative order of the items moving between have not changed and will
    raise an error if they have. If strict checking isn't desirable then you can call :meth:`~common_lib.ordered.move_before`,
    :meth:`~common_lib.ordered.move_after`, :meth:`~common_lib.ordered.move_start` or :meth:`~common_lib.ordered.move_end`.

    When saving an :code:`OrderedModel` the :code:`order_field_name` is excluded by default.
    This is to avoid overwriting a new ordering that may have changed after the record was
    loaded. To explicitly save the field pass it to :code:`update_fields` on :code:`save`.

    .. code-block:: python

        record.sort_key = move_after_record.sort_key + 1
        record.save(update_fields=['sort_key'])

    .. warning:: The value or :code:`order_field_name` on a record may be inconsistent with the database value after
        a save due to updates caused by database triggers. If you need to read the value after an update you should
        call :code:`refresh_from_db` or re-fetch the record.

    **Bulk Updates**

    In some cases you may wish to defer saving individual changes to ordering and instead save the entire state in
    one go. You can use :meth:`~django.db.models.query.QuerySet.bulk_update` and the trigger will happen once. Make
    sure to specify :code:`update_fields`.

    .. code-block:: python

        Shop.objects.bulk_update(shops, [Shop.order_field_name])

    If you specify :code:`batch_size` then things won't work properly as the trigger would run after each batch. To
    avoid problems with this or with saving multiple individual items you can use :meth:`~common_lib.ordered.OrderedModel.defer_triggers`.
    This will disable the normal triggers until the end of the context block and instead update the :code:`order_field_name`
    manually once at the end.

    **NOTE:** When using :code:`order_with_respect_to` this will update all rows in the table even if they don't require it.
    If using :code:`notify_on_reorder` it will fire even if nothing has changed.

    .. code-block:: python

        with Shop.defer_triggers():
            Shop.objects.bulk_update(
                shops_to_update, [Shop.order_field_name], batch_size=batch_size
            )
    """

    #: The name of the field to sort by. Your model must provide the field definition.
    order_field_name: str = "sort_key"
    #: If ordering is in respect to other field(s) specify them here
    order_with_respect_to: str | tuple[str, ...] | None = None
    notify_on_reorder: str | None = None
    """
    When specified pg_notify will be called with :code:`notify_on_reorder` as the channel name after a reorder occurs.

    Notifications will occur per update. If :code:`order_with_respect_to` is set it will happen once per unique grouping
    (eg. if a :code:`bulk_update` occurs across different groupings there will be mulitiple notifications).

    Notifications won't occur if an update happens that doesn't change any :code:`order_field_name` value.

    Notification payload is a JSON sting that looks like:

    .. code-block:: json

        {'operation': 'UPDATE',
         'order_with_respect_to': {'plaza': 116},
         'schema': 'public',
         'table': 'test_common_lib_shop',
         'timestamp': '2021-06-30 00:00:53.928499+00'}
    """

    objects = OrderedModelManager()

    # These are set by OrderedModelMetaClass
    _order_with_respect_to_fields: list[models.Field]
    _trigger_uris: list[str]  # pgtrigger trigger IDs

    class Meta:
        abstract = True

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        """Saves record but excludes :code:`order_field_name` by default"""
        if self.pk and update_fields is None:
            # By default exclude sort field name from being updated on save as it may
            # have changed if other records where added since this instance was loaded
            update_fields = []
            concrete_fields: list[Field] = self._meta.concrete_fields
            for field in concrete_fields:
                if (
                    not field.primary_key
                    and not hasattr(field, "through")
                    and field.attname != self.order_field_name
                ):
                    update_fields.append(field.attname)
        super().save(force_insert, force_update, using, update_fields)

    def _get_order_with_respect_to_filter(self):
        """Return :code:`Q` object that can filter queryset according to :code:`order_with_respect_to`"""
        filter = Q()
        if self.order_with_respect_to:
            for field in self._order_with_respect_to_fields:
                filter &= Q(**{field.column: getattr(self, field.column)})
        return filter

    def _move_by(self, relative_to: PkOrModel, amount: int):
        assert amount % 2 == 1, "amount must be odd"
        if isinstance(relative_to, self.__class__):
            relative_to = relative_to.pk
        with transaction.atomic():
            self.__class__._default_manager.filter(self._get_order_with_respect_to_filter()).filter(
                pk=self.pk
            ).select_for_update().update(
                **{
                    self.order_field_name: Subquery(
                        self.__class__._default_manager.filter(self._get_order_with_respect_to_filter())
                        .filter(pk=relative_to)
                        .values_list(self.order_field_name, flat=True)
                    )
                    + Value(amount)
                }
            )

    def move_before(self, before: PkOrModel):
        """Move this item before the specified record or primary key

        Args:
            before: Either the record or primary key of record to move this item before
        """
        self._move_by(before, -1)

    def move_after(self, after: PkOrModel):
        """Move this item after the specified record or primary key

        Args:
            after: Either the record or primary key of record to move this item after
        """
        self._move_by(after, 1)

    def move_start(self):
        """Move this item to the first position"""
        with transaction.atomic():
            self.__class__._default_manager.filter(self._get_order_with_respect_to_filter()).filter(
                pk=self.pk
            ).select_for_update().update(**{self.order_field_name: Value(0)})

    def move_end(self):
        """Move this item to the first position"""
        with transaction.atomic():
            self.__class__._default_manager.filter(self._get_order_with_respect_to_filter()).filter(
                pk=self.pk
            ).select_for_update().update(
                **{
                    self.order_field_name: Subquery(
                        self.__class__._default_manager.order_by(f"-{self.order_field_name}").values(
                            self.order_field_name
                        )[:1]
                    )
                    + Value(1)
                }
            )

    def move_between(self, before: PkOrModel, after: PkOrModel):
        """Insert this card between :code:`before` and :code:`after_pk`.

        Raises an error if :code:`before` and :code:`after` are no longer adjacent (eg. something else moved them)
        or the ordering of the current item has changed since it was loaded.
        """
        before_pk = before.pk if isinstance(before, models.Model) else before
        after_pk = after.pk if isinstance(after, models.Model) else after
        qs = self.__class__._default_manager.filter(pk__in=[self.pk, before_pk, after_pk]).select_for_update()
        with transaction.atomic():
            current = None
            first: OrderedModel | None = None
            second: OrderedModel | None = None
            for item in qs:
                if self.pk == item.pk:
                    current = item
                elif before_pk == item.pk:
                    first = item
                elif after_pk == item.pk:
                    second = item
            if not current:
                raise ValueError("item no longer exists")
            if getattr(current, self.order_field_name) != getattr(self, self.order_field_name):
                raise UnexpectedOrderError("item order has changed")

            if before_pk and not first or after_pk and not second:
                raise UnexpectedOrderError("before_pk / after_pk records not found")

            if first and second and self.order_with_respect_to:
                for field in self._order_with_respect_to_fields:
                    if getattr(first, field.column) != getattr(second, field.column):
                        raise UnexpectedOrderError(
                            f"Items {before_pk} and {after_pk} are no longer adjacent (different {field.column} values); aborting move"
                        )

            if after_pk is None:
                assert first is not None
                if (
                    self.__class__._default_manager.filter(
                        first._get_order_with_respect_to_filter()
                        & Q(**{self.order_field_name: getattr(first, self.order_field_name) + 2})
                    )
                    .order_by(self.order_field_name)
                    .exists()
                ):
                    raise UnexpectedOrderError(f"Item {before_pk} is no longer at the end of the list")
                setattr(self, self.order_field_name, getattr(first, self.order_field_name) + 1)
            elif before_pk is None:
                if getattr(second, self.order_field_name) != 2:
                    raise UnexpectedOrderError(f"Item {before_pk} is no longer at the start of the list")
                setattr(self, self.order_field_name, 0)
            else:
                if (getattr(second, self.order_field_name) - getattr(first, self.order_field_name)) != 2:
                    raise UnexpectedOrderError(
                        f"Items {before_pk} and {after_pk} are no longer adjacent; aborting move"
                    )
                setattr(self, self.order_field_name, getattr(first, self.order_field_name) + 1)
            update_fields = [self.order_field_name]
            if self.order_with_respect_to:
                for field in self._order_with_respect_to_fields:
                    value = getattr(first or second, field.column)
                    setattr(self, field.column, value)
                    update_fields.append(field.column)
            self.save(update_fields=update_fields)

    @classmethod
    def _get_order_with_respect_to_where_sql(cls, snapshot_name, prefix=""):
        """Get WHERE clause that filters by order_with_respect to

        snapshot_name is the name of snapshot in trigger (eg. `NEW` or transition table in update)
        """
        if not cls.order_with_respect_to:
            return ""
        return "WHERE " + "AND ".join(
            [
                f'"{f.column}" = {snapshot_name}."{prefix}{f.column}"'
                for f in cls._order_with_respect_to_fields
            ]
        )

    @classmethod
    def _generate_update_query(cls, where_clause=None):
        """Generates query that updates the ordering for a table

        If :code:`order_with_respect_to` is set then :code:`where_clause` should supply the
        necessary filters to restrict the query to the correct grouping.
        """
        table_name = cls._meta.db_table
        assert cls._meta.pk is not None
        pk_name = cls._meta.pk.name
        order_field_name = cls.order_field_name
        return f"""
           UPDATE {table_name} SET "{order_field_name}" = t.rn FROM (
             SELECT "{pk_name}", row_number() OVER (ORDER BY "{order_field_name}") * 2 as rn
             FROM "{table_name}" {where_clause}
           ) t
           WHERE t."{pk_name}" = "{table_name}"."{pk_name}";
        """

    @classmethod
    def _generate_notify_code(cls, snapshot_name=None, op="TG_OP", prefix=""):
        """Generate notification code.

        Sends a notification to channel identified by :code:`new_class.notify_on_reorder`. Payload
        is a json string that looks like:

        {'operation': 'UPDATE',
         'order_with_respect_to': {'plaza': 116},
         'notification_type': 'ORDERING',
         'originator_id': 'abc123',
         'schema': 'public',
         'table': 'test_common_lib_shop',
         'timestamp': '2021-06-30 00:00:53.928499+00'}

        order_with_respect_to will be `null` if not specified on the model.
        """
        if not cls.notify_on_reorder:
            return ""
        data = "'null'"
        if cls.order_with_respect_to:
            order_with_respect_to = cls.order_with_respect_to
            if isinstance(order_with_respect_to, str):
                order_with_respect_to = (order_with_respect_to,)
            order_with_respect_to_json_build = ",".join(
                [
                    f"'{fname}', {snapshot_name}.\"{prefix}{field.column}\""
                    for fname, field in zip(order_with_respect_to, cls._order_with_respect_to_fields)
                ]
            )
            data = f"""
               (SELECT json_build_object({order_with_respect_to_json_build}))
            """
        return f"""
           PERFORM pg_notify('{cls.notify_on_reorder}',
            '{{'
               || '"timestamp":"'            || CURRENT_TIMESTAMP      || '",'
               || '"notification_type":"'    || 'ORDERING'             || '",'
               || '"operation":"'            || {op}                   || '",'
               || '"schema":"'               || current_schema()       || '",'
               || '"table":"'                || '{cls._meta.db_table}' || '",'
               || '"originator_id":"'        || (SELECT COALESCE((SELECT NULLIF(CURRENT_SETTING('pghistory.context_metadata', 't'), ''))::json->>'originator_id', '')) || '",'
               || '"order_with_respect_to":' || {data}
               || '}}'               );
        """

    @classmethod
    @contextmanager
    def defer_triggers(cls, notification_op="UPDATE"):
        """A context manager that disables the ordering maintenance triggers and manually updates the ordering once at the end

        This is useful when you need to do multiple database writes the change the :code:`order_field_name` value and having
        the triggers run each time would cause issues.

        Usage::

            with Shop.defer_triggers():
                Shop.objects.bulk_update(
                    shops_to_update, [Shop.order_field_name], batch_size=10
                )

        .. warning:: When using :code:`order_with_respect_to` all rows in the table will be updated even if they don't
            require it. If using :code:`notify_on_reorder` it will fire even if nothing has changed and it will be fired
            for each unique combination of :code:`order_with_respect_to`.

        Args:
            notification_op: as it's not possible to automatically determine what operation actually happened within the
                context block any notifications will have :code:`operation` set to :code:`UPDATE`. If this is not correct
                for a particular use case pass :code:`notification_op="INSERT"` or :code:`notification_op="DELETE"` instead.
                Only relevant when :code:`notify_on_reorder`
                is set.
        """
        assert notification_op in ["UPDATE", "INSERT", "DELETE"]
        with pgtrigger.ignore(*cls._trigger_uris):
            try:
                yield
            finally:
                with connection.cursor() as cursor:
                    if cls.order_with_respect_to:
                        where_clause = cls._get_order_with_respect_to_where_sql("row")
                        columns = ", ".join([f.column for f in cls._order_with_respect_to_fields])
                        cursor.execute(
                            f"""
                        do
                            $$
                                declare
                                    row record;
                                begin
                                    for row in SELECT DISTINCT {columns} FROM {cls._meta.db_table} ORDER BY {columns}
                                        loop
                                            {cls._generate_update_query(where_clause)}
                                            {cls._generate_notify_code("row", op=f"'{notification_op}'")}
                                        end loop;
                                end;
                            $$
                        """
                        )
                    else:
                        cursor.execute(cls._generate_update_query())
                        cursor.execute(cls._generate_notify_code("row", op=f"'{notification_op}'"))
