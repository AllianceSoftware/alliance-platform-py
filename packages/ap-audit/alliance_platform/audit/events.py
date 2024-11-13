from alliance_platform.audit.registry import get_audited_fields
from alliance_platform.audit.utils import AuditEventProtocol
from alliance_platform.audit.utils import _get_name_from_label
from alliance_platform.audit.utils import get_model_module
from alliance_platform.audit.utils import is_m2m
from django.db import connection
from django.db import connections
from django.db import models
from django.db.models import sql
import pghistory
from pghistory import utils as pghistory_utils
from pghistory.core import _InsertEventCompiler
from pghistory.trigger import Event
from pghistory.trigger import _get_pgh_obj_pk_col
import pgtrigger


class PatchedEvent(Event):
    """
    Patched pghistory.trigger.event.

    This fixes the issue as seen here: https://github.com/jyveapp/django-pghistory/issues/9
    and also handles many-to-many (by copying values from the previous record if available).

    Limitation: because we copy the m2m values from prev. record, the value is not Guaranteed to be correct:
    it will be most of times, but would be empty if this gets instlalled on an existing model and no changes
    to m2m had been made since.

    """

    event_model: AuditEventProtocol  # type: ignore[assignment]

    def get_func(self, model):
        m2m_fields = {
            f.column: f'{self.row}."{f.column}"'
            for f in self.event_model._meta.fields
            if is_m2m(self.event_model.pgh_tracked_model, f.name)
        }
        event_model = self.event_model
        source_model = event_model.pgh_tracked_model
        fields = {
            f.column: f'{self.row}."{f.column}"' for f in get_audited_fields(source_model, ignore_m2m=True)
        }

        fields["pgh_created_at"] = "NOW()"
        fields["pgh_label"] = f"'{self.label}'"

        if hasattr(event_model, "pgh_obj"):
            fields["pgh_obj_id"] = f'{self.row}."{_get_pgh_obj_pk_col(event_model)}"'

        if hasattr(event_model, "pgh_context"):
            fields["pgh_context_id"] = "_pgh_attach_context()"

        # py36 support: until py37, the order of dict cannot be relied upon, so we'd better manually fix the order
        # (it will by default MOSTLY be fixed but its also stated to be unreliable before py37)
        col_keys = fields.keys()

        vals = ", ".join(fields[col] for col in col_keys)

        # for db fields, we wrap them inside "" quotes because some field names might be reserved
        # psql keywords eg "asc".
        cols = ", ".join(f'"{col}"' for col in col_keys)

        if not m2m_fields or not hasattr(event_model, "pgh_obj"):
            return f"""
                INSERT INTO "{event_model._meta.db_table}"
                    ({cols}) VALUES ({vals});
                RETURN NULL;
            """
        else:
            m2m_col_keys = m2m_fields.keys()
            m2m_queries = []
            for col in m2m_col_keys:
                sql = f"""(
                SELECT "{col}"
                FROM "{event_model._meta.db_table}"
                WHERE pgh_id=(
                    SELECT max(pgh_id) from {event_model._meta.db_table} where pgh_obj_id = {fields["pgh_obj_id"]}
                    )
                )"""
                m2m_queries.append(sql)

            m2m_vals = ", ".join(val for val in m2m_queries)
            m2m_cols = ", ".join(f'"{col}"' for col in m2m_col_keys)

            return f"""
                INSERT INTO "{event_model._meta.db_table}"
                    ({cols}, {m2m_cols}) VALUES ({vals}, {m2m_vals});
                RETURN NULL;
            """


class AuditSnapshot(pghistory.Tracker):
    """
    our Snapshot event. Audits AfterInsert, AfterUpdate and BeforeDelete. In the case
    of update, compares before<->after to see if any value gets modified; this means a
    ``instance.save()`` without any actual changes will NOT trigger an UPDATE snapshot.

    This also writes a self-referencing ``pgh_previous_id`` that points to last previous
    record for the same object: effectively a pgh_previous=ForeignKey('self', null=True)
    that can be used to find out what values have changed.

    Also audits many-to-many fields by placing triggers on the through table.
    """

    label: str

    def __init__(self, label=None):
        super().__init__(label=label)

    def setup(self, event_model):
        source_model = event_model.pgh_tracked_model

        set_previous = pgtrigger.Trigger(
            name=_get_name_from_label(self.label, "set_previous"),
            operation=pgtrigger.Insert,
            when=pgtrigger.Before,
            func=f"NEW.pgh_previous_id = (SELECT max(pgh_id) from {event_model._meta.db_table} where pgh_obj_id = NEW.pgh_obj_id); RETURN NEW;",
        )
        pgtrigger.register(set_previous)(event_model)

        insert_trigger = PatchedEvent(
            event_model=event_model,
            label="CREATE",
            name=_get_name_from_label(self.label, "insert"),
            snapshot="NEW",
            when=pgtrigger.After,
            operation=pgtrigger.Insert,
        )

        # we place a condition here to compare all values between the field in OLD and NEW: if they are
        # different ('__df'), then the condition is truthy. This is to ensure that any writes to db without
        # concrete changes will not trigger an UPDATE audit since nothing is different.
        condition = pgtrigger.Q()
        for field in get_audited_fields(source_model, ignore_m2m=True):
            condition |= pgtrigger.Q(**{f"old__{field.name}__df": pgtrigger.F(f"new__{field.name}")})
        update_trigger = PatchedEvent(
            event_model=event_model,
            label="UPDATE",
            name=_get_name_from_label(self.label, "update"),
            snapshot="NEW",
            when=pgtrigger.After,
            operation=pgtrigger.Update,
            condition=condition,
        )

        delete_trigger = PatchedEvent(
            event_model=event_model,
            label="DELETE",
            name=_get_name_from_label(self.label, "delete"),
            snapshot="OLD",
            when=None,
            operation=pgtrigger.Delete,
        )

        pgtrigger.register(insert_trigger, update_trigger, delete_trigger)(source_model)

        m2ms = []  # list[Tuple(many to many field, through table of that field)]
        if source_model._meta.many_to_many:
            for m2m in source_model._meta.many_to_many:
                m2mt = getattr(source_model, m2m.name).through
                if type(m2mt) is str:
                    raise AttributeError(
                        f'The through table "{m2mt}" for model {source_model} is currently a string. This likely means you have manually defined through model, and its not yet available. Through models need to be defined before your event model.'
                    )
                m2ms.append((m2m, m2mt))

        for m2m, m2mt in m2ms:
            db_column_for_source_model_in_m2m = getattr(m2mt, m2m.m2m_field_name()).field.column
            db_column_for_target_model_in_m2m = getattr(m2mt, m2m.m2m_reverse_field_name()).field.column

            original_columns_list = [
                f.column
                for f in event_model._meta.fields
                if not isinstance(f, models.AutoField) and hasattr(source_model, f.name)
            ]

            if m2m.name not in original_columns_list:  # the m2m field was excluded
                continue

            original_columns_list.remove(m2m.name)

            pghistory_columns_list = ["pgh_created_at", "pgh_label", "pgh_obj_id", "pgh_context_id"]

            original_columns = ", ".join(f'"{col}"' for col in original_columns_list)
            pghistory_columns = ", ".join(f'"{col}"' for col in pghistory_columns_list)

            # for many to many changes, we watch the action happening on the through table, and when
            # an event is observed, we:
            #  - creates a new row in the log table for main model, with exactly same values as previous one,
            #  - but replaces the many-to-many field value with values looked up from the through table
            #    after the change.

            # Create proxy class so gets detected by migration system
            proxy_attr_name = f"{m2m.name}_AuditEventProxy"
            proxy_class_name = f"{source_model._meta.label.replace('.', '_')}_{m2m.name}_AuditEventProxy"
            proxy_class = type(
                proxy_class_name,
                (m2mt,),
                {
                    "Meta": type("Meta", (), {"proxy": True}),
                    "__module__": get_model_module(m2mt),
                    "__qualname__": f"{source_model.__qualname__}.{proxy_attr_name}",
                },
            )
            setattr(source_model, proxy_attr_name, proxy_class)

            pgtrigger.register(
                pgtrigger.Trigger(
                    name=_get_name_from_label(self.label + "_" + m2m.name, "m2m_add"),
                    operation=pgtrigger.Insert,
                    when=pgtrigger.After,
                    func=f"""
                        INSERT INTO "{event_model._meta.db_table}" ({original_columns}, {pghistory_columns}, "{m2m.name}")
                            SELECT {original_columns}, NOW(), 'UPDATE', NEW."{db_column_for_source_model_in_m2m}", _pgh_attach_context(), (
                                SELECT array_agg("{db_column_for_target_model_in_m2m}")
                                FROM {m2mt._meta.db_table}
                                WHERE {db_column_for_source_model_in_m2m}=NEW."{db_column_for_source_model_in_m2m}"
                            )
                            FROM "{event_model._meta.db_table}"
                            WHERE pgh_obj_id=NEW."{db_column_for_source_model_in_m2m}"
                            ORDER BY pgh_id DESC
                            LIMIT 1;
                        RETURN NULL;
                    """,
                )
            )(proxy_class)

            pgtrigger.register(
                pgtrigger.Trigger(
                    name=_get_name_from_label(self.label + "_" + m2m.name, "m2m_remove"),
                    operation=pgtrigger.Delete,
                    when=pgtrigger.After,
                    func=f"""
                        INSERT INTO "{event_model._meta.db_table}" ({original_columns}, {pghistory_columns}, "{m2m.name}")
                            SELECT {original_columns}, NOW(), 'UPDATE', OLD."{db_column_for_source_model_in_m2m}", _pgh_attach_context(), (
                                SELECT array_agg("{db_column_for_target_model_in_m2m}")
                                FROM {m2mt._meta.db_table}
                                WHERE {db_column_for_source_model_in_m2m}=OLD."{db_column_for_source_model_in_m2m}"
                            )
                            FROM "{event_model._meta.db_table}"
                            WHERE pgh_obj_id=OLD."{db_column_for_source_model_in_m2m}"
                            ORDER BY pgh_id DESC
                            LIMIT 1;
                        RETURN NULL;
                    """,
                )
            )(proxy_class)


def create_event(obj, registration, *, label, using="default"):
    """
    Patched pghistory.core.create_event.

    Dropped event registration check as it's already done in create_audit_event, and
    also adds M2M fields handling support.
    """

    event_model = registration.event_model
    event_model_kwargs = {
        "pgh_label": label,
        **{
            field.attname: getattr(obj, field.attname)
            for field in event_model._meta.fields
            if (not field.name.startswith("pgh_") and not is_m2m(event_model.pgh_tracked_model, field.name))
        },
    }  # copy all fields except m2m. for m2m we fetch and fill directly.

    event_model_kwargs.update(
        {
            **{
                field.attname: list(
                    getattr(obj, field.attname).values_list(
                        event_model.pgh_tracked_model._meta.get_field(field.name).target_field.attname,
                        flat=True,
                    )
                )
                for field in event_model._meta.fields
                if (not field.name.startswith("pgh_") and is_m2m(event_model.pgh_tracked_model, field.name))
            },
        }
    )

    if hasattr(event_model, "pgh_obj"):
        event_model_kwargs["pgh_obj"] = obj

    event_obj = event_model(**event_model_kwargs)

    # The event model is inserted manually with a custom SQL compiler
    # that attaches the context using the _pgh_attach_context
    # stored procedure. Django does not allow one to use F()
    # objects to reference stored procedures, so we have to
    # inject it with a custom SQL compiler here.
    query = sql.InsertQuery(event_model)
    query.insert_values(
        [field for field in event_model._meta.fields if not isinstance(field, models.AutoField)],
        [event_obj],
    )
    if pghistory_utils.psycopg_maj_version == 3:
        from pghistory.core import Literal
        from pghistory.core import LiteralDumper

        connections[using].connection.adapters.register_dumper(Literal, LiteralDumper)
    vals = _InsertEventCompiler(query, connection, using=using).execute_sql(event_model._meta.fields)

    # Django >= 3.1 returns the values as a list of one element
    for field, val in zip(event_model._meta.fields, vals[0]):
        setattr(event_obj, field.attname, val)

    return event_obj
